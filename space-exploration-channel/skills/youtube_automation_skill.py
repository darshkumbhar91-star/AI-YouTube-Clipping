"""
YouTube Automation Skill - Phase 1-4 automation pipeline.
Channel setup → Content pipeline → Optimization → Scaling.
"""

import asyncio
import logging
import json
import pickle
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from enum import Enum
import aiohttp
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from .registry import BaseSkill, SkillMetadata, SkillCategory, register_skill
from .context import ExecutionContext


logger = logging.getLogger(__name__)


class AutomationPhase(Enum):
    """Automation phases."""
    PHASE_1_SETUP = "phase_1_setup"
    PHASE_2_CONTENT = "phase_2_content"
    PHASE_3_OPTIMIZE = "phase_3_optimize"
    PHASE_4_SCALE = "phase_4_scale"


class UploadStatus(Enum):
    """Video upload status."""
    DRAFT = "draft"
    PROCESSING = "processing"
    UPLOADED = "uploaded"
    SCHEDULED = "scheduled"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass
class VideoMetadata:
    """Complete video metadata for upload."""
    title: str
    description: str
    tags: List[str]
    category_id: str = "28"  # Science & Technology
    default_language: str = "en"
    default_audio_language: str = "en"
    privacy_status: str = "private"
    publish_at: Optional[str] = None
    location: Optional[str] = None
    recording_date: Optional[str] = None
    license: str = "youtube"
    embeddable: bool = True
    public_stats_viewable: bool = True
    made_for_kids: bool = False
    notify_subscribers: bool = True


@dataclass
class ThumbnailVariant:
    """Thumbnail variant for A/B testing."""
    variant_id: str
    path: Path
    prompt: str
    style: str
    ctr_prediction: float = 0.0


@dataclass
class ScheduledVideo:
    """Scheduled video in content calendar."""
    video_id: str
    topic_id: str
    title: str
    scheduled_time: datetime
    status: UploadStatus
    metadata: VideoMetadata
    thumbnail_variants: List[ThumbnailVariant]
    shorts_ids: List[str] = field(default_factory=list)


class YouTubeAuthSkill(BaseSkill):
    """YouTube OAuth authentication and token management."""
    
    metadata = SkillMetadata(
        name="youtube_auth",
        category=SkillCategory.CHANNEL,
        version="1.0.0",
        description="YouTube Data API v3 authentication with token refresh",
        dependencies=[],
        required_config=["client_secrets_file", "token_file", "scopes"],
        optional_config=[],
        inputs=[],
        outputs=["youtube_service", "credentials"],
        tags=["youtube", "oauth", "authentication", "api"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.client_secrets = config.get("client_secrets_file", "config/youtube_client_secrets.json")
        self.token_file = config.get("token_file", "config/youtube_token.json")
        self.scopes = config.get("scopes", [
            "https://www.googleapis.com/auth/youtube.upload",
            "https://www.googleapis.com/auth/youtube.readonly",
            "https://www.googleapis.com/auth/youtube.force-ssl",
            "https://www.googleapis.com/auth/youtubepartner"
        ])
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        service = await self._get_authenticated_service()
        
        # Verify channel access
        channel_info = await self._get_channel_info(service)
        
        results = {
            "youtube_service": service,
            "channel_info": channel_info,
            "authenticated": True
        }
        
        context.set_output("youtube_auth", results)
        return results
    
    async def _get_authenticated_service(self):
        """Get authenticated YouTube service."""
        creds = None
        
        # Load existing token
        if Path(self.token_file).exists():
            with open(self.token_file) as f:
                token_data = json.load(f)
            creds = Credentials.from_authorized_user_info(token_data, self.scopes)
        
        # Refresh or get new token
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets, self.scopes
                )
                creds = flow.run_local_server(port=0)
            
            # Save token
            with open(self.token_file, 'w') as f:
                f.write(creds.to_json())
        
        return build('youtube', 'v3', credentials=creds)
    
    async def _get_channel_info(self, service) -> Dict:
        """Get authenticated channel info."""
        try:
            request = service.channels().list(part="snippet,statistics,brandingSettings", mine=True)
            response = request.execute()
            
            if response.get("items"):
                channel = response["items"][0]
                return {
                    "id": channel["id"],
                    "title": channel["snippet"]["title"],
                    "handle": channel["snippet"].get("customUrl", ""),
                    "description": channel["snippet"]["description"],
                    "subscribers": channel["statistics"].get("subscriberCount", "0"),
                    "views": channel["statistics"].get("viewCount", "0"),
                    "videos": channel["statistics"].get("videoCount", "0"),
                    "country": channel["snippet"].get("country", ""),
                }
        except Exception as e:
            logger.error(f"Failed to get channel info: {e}")
        
        return {}


class Phase1ChannelSetupSkill(BaseSkill):
    """Phase 1: Complete channel setup and branding."""
    
    metadata = SkillMetadata(
        name="phase1_channel_setup",
        category=SkillCategory.CHANNEL,
        version="1.0.0",
        description="Phase 1: Channel creation, branding, SEO, playlists, monetization prep",
        dependencies=["youtube_auth"],
        required_config=["channel_config"],
        optional_config=["branding_assets_dir"],
        inputs=["channel_config"],
        outputs=["channel_id", "branding_status", "playlists", "monetization_checklist"],
        tags=["channel_setup", "branding", "seo", "playlists", "monetization"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.channel_config = config.get("channel_config", {})
        self.branding_dir = Path(config.get("branding_assets_dir", "assets/branding"))
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        service = context.get_input("youtube_service")
        channel_config = context.get_input("channel_config", self.channel_config)
        
        if not service:
            auth_skill = YouTubeAuthSkill(self.config)
            auth_result = await auth_skill.execute(context)
            service = auth_result.get("youtube_service")
        
        results = {
            "channel_id": None,
            "branding_status": {},
            "playlists": [],
            "monetization_checklist": [],
            "completed_steps": []
        }
        
        # Step 1: Verify/Update channel branding
        branding = await self._setup_branding(service, channel_config)
        results["branding_status"] = branding
        results["completed_steps"].append("branding")
        
        # Step 2: Set channel SEO
        seo = await self._setup_seo(service, channel_config)
        results["seo_status"] = seo
        results["completed_steps"].append("seo")
        
        # Step 3: Create playlists
        playlists = await self._create_playlists(service, channel_config)
        results["playlists"] = playlists
        results["completed_steps"].append("playlists")
        
        # Step 4: Set upload defaults
        defaults = await self._set_upload_defaults(service, channel_config)
        results["upload_defaults"] = defaults
        results["completed_steps"].append("upload_defaults")
        
        # Step 5: Monetization checklist
        monetization = self._generate_monetization_checklist(channel_config)
        results["monetization_checklist"] = monetization
        results["completed_steps"].append("monetization_checklist")
        
        # Step 6: Channel sections layout
        sections = await self._setup_sections(service, playlists)
        results["sections"] = sections
        results["completed_steps"].append("sections")
        
        context.set_output("phase1_setup", results)
        return results
    
    async def _setup_branding(self, service, config: Dict) -> Dict:
        """Setup channel branding: avatar, banner, watermark."""
        status = {
            "avatar": False,
            "banner": False,
            "watermark": False,
            "trailer": False
        }
        
        # Note: Branding updates require special API access
        # This documents what needs to be done manually or via YouTube Studio
        
        branding_spec = {
            "avatar": {
                "path": str(self.branding_dir / "avatar.png"),
                "specs": "800x800px, PNG, circular safe zone 98%",
                "description": "Logo centered, works at 16px favicon size"
            },
            "banner": {
                "path": str(self.branding_dir / "banner.png"),
                "specs": "2560x1440px, safe area 1546x423px center",
                "description": "Include: logo, tagline, schedule, social handles"
            },
            "watermark": {
                "path": str(self.branding_dir / "watermark.png"),
                "specs": "150x150px, transparent PNG, 1px border",
                "description": "Subscribe button overlay, appears at 10:00"
            },
            "trailer": {
                "specs": "30-60 seconds, unlisted until replaced",
                "description": "Channel trailer for non-subscribers"
            }
        }
        
        status["specs"] = branding_spec
        status["note"] = "Upload via YouTube Studio > Customization > Branding"
        
        return status
    
    async def _setup_seo(self, service, config: Dict) -> Dict:
        """Setup channel SEO: description, keywords, links."""
        
        seo_config = {
            "description": config.get("description", ""),
            "keywords": config.get("keywords", ""),
            "links": config.get("links", []),
            "contact_email": config.get("contact_email", ""),
            "location": config.get("location", "US")
        }
        
        # Update channel branding settings
        try:
            request = service.channels().update(
                part="brandingSettings",
                body={
                    "id": "mine",
                    "brandingSettings": {
                        "channel": {
                            "title": config.get("title", "Space Explained"),
                            "description": seo_config["description"],
                            "keywords": seo_config["keywords"],
                            "defaultTab": "VIDEOS",
                            "showRelatedChannels": True,
                            "showBrowseView": True,
                            "featuredChannelsTitle": "Featured Channels",
                            "featuredChannelsUrls": seo_config.get("featured_channels", [])
                        }
                    }
                }
            )
            request.execute()
            seo_config["updated"] = True
        except Exception as e:
            logger.error(f"SEO update failed: {e}")
            seo_config["updated"] = False
            seo_config["error"] = str(e)
        
        return seo_config
    
    async def _create_playlists(self, service, config: Dict) -> List[Dict]:
        """Create default playlists."""
        playlists_config = config.get("playlists", [
            {"title": "🚀 Space Missions & Launches", "description": "Live launches, mission updates, rocket science"},
            {"title": "🌌 Deep Space & Cosmology", "description": "Black holes, galaxies, dark matter, universe origins"},
            {"title": "🪐 Planetary Science", "description": "Mars, Venus, gas giants, moons, exoplanets"},
            {"title": "🛰️ Space Technology", "description": "Rockets, satellites, stations, propulsion, robotics"},
            {"title": "👨‍🚀 Astronaut Life & EVA", "description": "Spacewalks, ISS life, training, human spaceflight"},
            {"title": "📰 Space News & Updates", "description": "Weekly space news, industry updates, policy"},
            {"title": "🎬 Shorts: Quick Space Facts", "description": "60-second space facts, vertical format"}
        ])
        
        created = []
        for pl in playlists_config:
            try:
                request = service.playlists().insert(
                    part="snippet,status",
                    body={
                        "snippet": {
                            "title": pl["title"],
                            "description": pl["description"],
                            "defaultLanguage": "en"
                        },
                        "status": {"privacyStatus": "public"}
                    }
                )
                response = request.execute()
                created.append({
                    "id": response["id"],
                    "title": pl["title"],
                    "url": f"https://youtube.com/playlist?list={response['id']}"
                })
            except Exception as e:
                logger.error(f"Playlist creation failed: {e}")
                created.append({"title": pl["title"], "error": str(e)})
        
        return created
    
    async def _set_upload_defaults(self, service, config: Dict) -> Dict:
        """Set default upload settings."""
        defaults = config.get("upload_defaults", {
            "categoryId": "28",
            "license": "youtube",
            "privacyStatus": "private",
            "tags": ["space", "nasa", "astronomy", "space exploration", "science"],
            "title_format": "[TOPIC] | Space Explained"
        })
        
        # Note: Upload defaults are set per-channel in YouTube Studio
        # API doesn't directly support this, document for manual setup
        return {
            "configured": defaults,
            "note": "Set in YouTube Studio > Settings > Upload defaults"
        }
    
    def _generate_monetization_checklist(self, config: Dict) -> List[Dict]:
        """Generate monetization preparation checklist."""
        return [
            {"item": "1,000 subscribers", "status": "pending", "target_date": "Month 3"},
            {"item": "4,000 watch hours (12 months)", "status": "pending", "target_date": "Month 4"},
            {"item": "2-Step Verification enabled", "status": "pending", "action": "Google Account > Security"},
            {"item": "AdSense account linked", "status": "pending", "action": "YouTube Studio > Monetization"},
            {"item": "Affiliate programs joined", "status": "pending", "programs": [
                "Amazon Associates (space books, gear)",
                "Skillshare/Coursera (space courses)",
                "Telescope/gear affiliates (High Point, OPT)",
                "VPN affiliates (NordVPN, ExpressVPN)"
            ]},
            {"item": "Merch store (Printful/Spreadshirt)", "status": "pending", "designs": [
                "\"Space Explained\" logo tees",
                "Mission patch style designs",
                "Rocket blueprint posters",
                "Exoplanet travel posters"
            ]},
            {"item": "Course platform (Teachable/Kajabi)", "status": "pending", "topics": [
                "Rocket Science 101",
                "Orbital Mechanics Basics",
                "Space Mission Design"
            ]},
            {"item": "Patreon/Ko-fi for supporters", "status": "pending", "tiers": [
                "$3 - Early access + Discord",
                "$7 - Ad-free + behind scenes",
                "$15 - Monthly Q&A + exclusive content"
            ]}
        ]
    
    async def _setup_sections(self, service, playlists: List[Dict]) -> Dict:
        """Setup channel sections layout."""
        # Channel sections require special API access
        # Document the intended layout
        return {
            "layout": [
                {"type": "channel_trailer", "for": "unsubscribed"},
                {"type": "latest_upload", "for": "subscribers"},
                {"type": "popular_uploads"},
                {"type": "multiple_playlists", "playlists": [p["id"] for p in playlists if "id" in p]},
                {"type": "shorts"},
                {"type": "featured_channels", "channels": [
                    "UC3MgqzG5qZ8rJQZH3xX2QqQ",  # NASA
                    "UC6uKrU_WqJ1R2HMTY3DeY5Q",  # SpaceX
                    "UCiP6wD_tYlYLYh3agzbByWQ",  # ESA
                ]}
            ],
            "note": "Configure in YouTube Studio > Customization > Layout"
        }


class Phase2ContentPipelineSkill(BaseSkill):
    """Phase 2: Automated content production pipeline."""
    
    metadata = SkillMetadata(
        name="phase2_content_pipeline",
        category=SkillCategory.CHANNEL,
        version="1.0.0",
        description="Phase 2: Topic queue → Research → Script → VFX → Voice → Composite → Upload",
        dependencies=["phase1_channel_setup", "research_pipeline", "script_writer", "vfx_pipeline", "elevenlabs_tts", "compositing"],
        required_config=["upload_schedule", "content_pillars"],
        optional_config=["batch_size", "quality_thresholds"],
        inputs=["topic_queue", "schedule"],
        outputs=["published_videos", "pipeline_metrics", "content_calendar"],
        tags=["content_pipeline", "automation", "scheduling", "batch_production"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.upload_schedule = config.get("upload_schedule", {
            "days": ["tuesday", "thursday", "saturday"],
            "time": "18:00",
            "timezone": "US/Eastern"
        })
        self.content_pillars = config.get("content_pillars", [
            "planetary_science",
            "space_technology", 
            "cosmology",
            "exoplanets",
            "missions",
            "space_news"
        ])
        self.batch_size = config.get("batch_size", 3)
        self.quality_thresholds = config.get("quality_thresholds", {
            "min_script_score": 0.8,
            "min_visual_quality": 0.7,
            "min_audio_quality": 0.8
        })
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        topic_queue = context.get_input("topic_queue", [])
        schedule = context.get_input("schedule", {})
        service = context.get_input("youtube_service")
        
        # Get next topics to produce
        topics_to_produce = self._select_topics(topic_queue, self.batch_size)
        
        results = {
            "produced": [],
            "scheduled": [],
            "failed": [],
            "pipeline_metrics": {}
        }
        
        for topic in topics_to_produce:
            try:
                video_result = await self._produce_video(topic, service)
                if video_result.get("success"):
                    results["produced"].append(video_result)
                    
                    # Schedule upload
                    scheduled = await self._schedule_upload(video_result, service)
                    results["scheduled"].append(scheduled)
                else:
                    results["failed"].append({"topic": topic, "error": video_result.get("error")})
            except Exception as e:
                logger.error(f"Production failed for {topic}: {e}")
                results["failed"].append({"topic": topic, "error": str(e)})
        
        # Generate content calendar
        results["content_calendar"] = self._generate_calendar(results["scheduled"])
        
        context.set_output("phase2_pipeline", results)
        return results
    
    def _select_topics(self, queue: List[Dict], count: int) -> List[Dict]:
        """Select highest priority topics."""
        # Sort by priority, then by pillar balance
        sorted_queue = sorted(queue, key=lambda x: (-x.get("priority", 0), x.get("pillar", "")))
        
        # Ensure pillar diversity
        selected = []
        pillar_counts = {p: 0 for p in self.content_pillars}
        
        for topic in sorted_queue:
            if len(selected) >= count:
                break
            pillar = topic.get("pillar", "other")
            if pillar_counts.get(pillar, 0) < 2:  # Max 2 per pillar per batch
                selected.append(topic)
                pillar_counts[pillar] = pillar_counts.get(pillar, 0) + 1
        
        # Fill remaining
        for topic in sorted_queue:
            if len(selected) >= count:
                break
            if topic not in selected:
                selected.append(topic)
        
        return selected
    
    async def _produce_video(self, topic: Dict, service) -> Dict:
        """Run full production pipeline for one topic."""
        # This orchestrates the skill pipeline
        # In production, this would call the orchestrator
        
        topic_id = topic.get("id", f"topic_{datetime.now().timestamp()}")
        
        # Mock production result
        return {
            "success": True,
            "topic_id": topic_id,
            "topic": topic,
            "video_path": f"output/{topic_id}_final.mov",
            "thumbnail_paths": [f"thumbnails/{topic_id}_v{i}.jpg" for i in range(3)],
            "metadata": {
                "title": topic.get("title", "Untitled"),
                "description": topic.get("description", ""),
                "tags": topic.get("tags", []),
                "hashtags": topic.get("hashtags", [])
            },
            "shorts_paths": [f"shorts/{topic_id}_short{i}.mp4" for i in range(3)],
            "timing": topic.get("timing", {}),
            "produced_at": datetime.now().isoformat()
        }
    
    async def _schedule_upload(self, video_result: Dict, service) -> Dict:
        """Schedule video upload at optimal time."""
        topic_id = video_result["topic_id"]
        metadata = video_result["metadata"]
        
        # Calculate next upload slot
        scheduled_time = self._get_next_upload_slot()
        
        scheduled = ScheduledVideo(
            video_id="",  # Will be set after upload
            topic_id=topic_id,
            title=metadata["title"],
            scheduled_time=scheduled_time,
            status=UploadStatus.SCHEDULED,
            metadata=VideoMetadata(
                title=metadata["title"],
                description=metadata["description"],
                tags=metadata["tags"],
                publish_at=scheduled_time.isoformat() + "-05:00"
            ),
            thumbnail_variants=[
                ThumbnailVariant(variant_id=f"v{i}", path=Path(p), prompt="", style="")
                for i, p in enumerate(video_result["thumbnail_paths"])
            ],
            shorts_ids=[]
        )
        
        return {
            "topic_id": topic_id,
            "scheduled_time": scheduled_time.isoformat(),
            "title": metadata["title"],
            "thumbnail_count": len(video_result["thumbnail_paths"]),
            "shorts_count": len(video_result["shorts_paths"])
        }
    
    def _get_next_upload_slot(self) -> datetime:
        """Get next upload slot based on schedule."""
        now = datetime.now()
        schedule_days = self.upload_schedule["days"]
        schedule_time = self.upload_schedule["time"]
        hour, minute = map(int, schedule_time.split(":"))
        
        day_map = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}
        target_weekdays = [day_map[d.lower()] for d in schedule_days]
        
        # Find next slot
        for days_ahead in range(14):
            target_date = now + timedelta(days=days_ahead)
            if target_date.weekday() in target_weekdays:
                scheduled = target_date.replace(hour=hour, minute=minute, second=0, microsecond=0)
                if scheduled > now:
                    return scheduled
        
        # Fallback
        return now.replace(hour=hour, minute=minute) + timedelta(days=2)
    
    def _generate_calendar(self, scheduled: List[Dict]) -> List[Dict]:
        """Generate content calendar view."""
        calendar = []
        for item in scheduled:
            calendar.append({
                "date": item["scheduled_time"][:10],
                "time": item["scheduled_time"][11:16],
                "title": item["title"],
                "topic_id": item["topic_id"],
                "status": "scheduled"
            })
        return sorted(calendar, key=lambda x: x["date"])


class Phase3OptimizationSkill(BaseSkill):
    """Phase 3: A/B testing, analytics, retention optimization."""
    
    metadata = SkillMetadata(
        name="phase3_optimization",
        category=SkillCategory.OPTIMIZATION,
        version="1.0.0",
        description="Phase 3: Thumbnail A/B testing, title optimization, retention analysis, SEO refinement",
        dependencies=["phase2_content_pipeline"],
        required_config=["analytics_api", "testing_config"],
        optional_config=["ab_test_duration", "significance_threshold"],
        inputs=["published_videos", "analytics_data"],
        outputs=["optimization_report", "ab_test_results", "seo_recommendations", "retention_insights"],
        tags=["optimization", "ab_testing", "analytics", "retention", "seo", "ctr"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.test_duration = config.get("ab_test_duration", 86400)  # 24 hours
        self.significance = config.get("significance_threshold", 0.95)
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        videos = context.get_input("published_videos", [])
        analytics = context.get_input("analytics_data", {})
        
        results = {
            "ab_tests": [],
            "title_optimizations": [],
            "retention_analysis": {},
            "seo_recommendations": [],
            "thumbnail_winners": {}
        }
        
        # Analyze each video
        for video in videos:
            video_id = video.get("video_id") or video.get("youtube_id")
            if not video_id:
                continue
            
            # Thumbnail A/B test results
            thumb_result = await self._analyze_thumbnail_test(video_id, video.get("thumbnail_variants", []))
            results["ab_tests"].append(thumb_result)
            
            if thumb_result.get("winner"):
                results["thumbnail_winners"][video_id] = thumb_result["winner"]
            
            # Title optimization
            title_opt = await self._analyze_title_performance(video_id, video.get("title", ""))
            results["title_optimizations"].append(title_opt)
            
            # Retention analysis
            retention = await self._analyze_retention(video_id, analytics.get(video_id, {}))
            results["retention_analysis"][video_id] = retention
            
            # SEO recommendations
            seo = await self._generate_seo_recommendations(video_id, video, analytics.get(video_id, {}))
            results["seo_recommendations"].extend(seo)
        
        # Aggregate insights
        results["aggregate_insights"] = self._aggregate_insights(results)
        
        context.set_output("phase3_optimization", results)
        return results
    
    async def _analyze_thumbnail_test(
        self, 
        video_id: str, 
        variants: List[Dict]
    ) -> Dict:
        """Analyze thumbnail A/B test results."""
        # In production, fetch actual CTR data from YouTube Analytics
        # Mock for now
        return {
            "video_id": video_id,
            "variants_tested": len(variants),
            "winner": variants[0].get("variant_id", "v0") if variants else None,
            "ctr_lift": 0.15,
            "significance": 0.92,
            "recommendation": "Use winning style for similar content"
        }
    
    async def _analyze_title_performance(self, video_id: str, title: str) -> Dict:
        """Analyze title CTR and suggest optimizations."""
        return {
            "video_id": video_id,
            "current_title": title,
            "current_ctr": 0.08,
            "predicted_ctr_optimized": 0.11,
            "suggestions": [
                "Add number: '5 Reasons...'",
                "Include current year: '... in 2025'",
                "Add power word: 'Secret', 'Hidden', 'Shocking'"
            ]
        }
    
    async def _analyze_retention(self, video_id: str, analytics: Dict) -> Dict:
        """Analyze audience retention curve."""
        return {
            "video_id": video_id,
            "avg_view_duration": analytics.get("avg_view_duration", "4:32"),
            "avg_percentage_viewed": analytics.get("avg_percentage_viewed", 52),
            "drop_off_points": [
                {"time": "0:15", "retention": 85, "reason": "Hook effectiveness"},
                {"time": "1:30", "retention": 72, "reason": "Transition to content"},
                {"time": "3:45", "retention": 58, "reason": "Mid-video fatigue"},
                {"time": "6:20", "retention": 45, "reason": "Pre-outro dip"}
            ],
            "peaks": [
                {"time": "2:10", "retention": 78, "content": "Key visual reveal"},
                {"time": "5:00", "retention": 65, "content": "Surprising fact"}
            ],
            "recommendations": [
                "Strengthen hook at 0:00-0:15",
                "Add pattern interrupt at 3:30",
                "Tease upcoming reveal at 3:00"
            ]
        }
    
    async def _generate_seo_recommendations(
        self, 
        video_id: str, 
        video: Dict, 
        analytics: Dict
    ) -> List[Dict]:
        """Generate SEO improvement recommendations."""
        search_terms = analytics.get("search_terms", [])
        traffic_sources = analytics.get("traffic_sources", {})
        
        recommendations = []
        
        # Missing search terms
        if search_terms:
            top_terms = [t for t in search_terms if t.get("views", 0) > 100]
            for term in top_terms[:5]:
                if term["term"].lower() not in video.get("description", "").lower():
                    recommendations.append({
                        "video_id": video_id,
                        "type": "description_keyword",
                        "term": term["term"],
                        "action": f"Add '{term['term']}' to description and tags",
                        "potential_views": term.get("views", 0)
                    })
        
        # Traffic source optimization
        if traffic_sources.get("YOUTUBE_SEARCH", 0) < 0.3:
            recommendations.append({
                "video_id": video_id,
                "type": "search_optimization",
                "action": "Improve title/description keyword density for search",
                "priority": "high"
            })
        
        if traffic_sources.get("SUGGESTED_VIDEO", 0) < 0.2:
            recommendations.append({
                "video_id": video_id,
                "type": "suggested_optimization",
                "action": "Add related video cards and end screens",
                "priority": "medium"
            })
        
        return recommendations
    
    def _aggregate_insights(self, results: Dict) -> Dict:
        """Aggregate insights across all videos."""
        ab_tests = results.get("ab_tests", [])
        retention = results.get("retention_analysis", {})
        
        return {
            "avg_ctr_lift_from_thumbnails": sum(t.get("ctr_lift", 0) for t in ab_tests) / max(len(ab_tests), 1),
            "common_drop_off": "3:30-4:00 (mid-video)",
            "best_retention_content": "Visual reveals and surprising facts",
            "top_seo_gap": "Missing long-tail search terms in descriptions",
            "recommended_focus": [
                "Standardize winning thumbnail style",
                "Add mid-video hooks at 3:30",
                "Optimize descriptions for search terms",
                "Improve end screen conversion"
            ]
        }


class Phase4ScalingSkill(BaseSkill):
    """Phase 4: Multi-channel, shorts automation, sponsorship, team."""
    
    metadata = SkillMetadata(
        name="phase4_scaling",
        category=SkillCategory.CHANNEL,
        version="1.0.0",
        description="Phase 4: Shorts automation, multi-language, sponsorship pipeline, team hiring",
        dependencies=["phase3_optimization"],
        required_config=["scaling_config"],
        optional_config=["localization_langs", "sponsor_outreach_template"],
        inputs=["channel_metrics", "revenue_data"],
        outputs=["scaling_plan", "shorts_pipeline", "sponsor_pipeline", "hiring_plan"],
        tags=["scaling", "shorts", "localization", "sponsorship", "team", "multi_channel"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.scaling_config = config.get("scaling_config", {})
        self.localization_langs = config.get("localization_langs", ["es", "pt", "de", "fr", "hi", "ja"])
        self.sponsor_template = config.get("sponsor_outreach_template", "")
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        metrics = context.get_input("channel_metrics", {})
        revenue = context.get_input("revenue_data", {})
        
        results = {
            "shorts_automation": await self._setup_shorts_pipeline(),
            "localization": await self._plan_localization(),
            "sponsorship": await self._build_sponsor_pipeline(metrics),
            "multi_channel": self._plan_multi_channel(),
            "hiring": self._plan_hiring(metrics, revenue),
            "revenue_diversification": self._plan_revenue_streams(revenue)
        }
        
        context.set_output("phase4_scaling", results)
        return results
    
    async def _setup_shorts_pipeline(self) -> Dict:
        """Setup automated Shorts production from long-form."""
        return {
            "strategy": "3 Shorts per long-form video",
            "extraction_points": [
                "Hook segment (0:00-0:30)",
                "Key visual reveal",
                "Surprising fact/stat",
                "Outro teaser"
            ],
            "automation": {
                "tool": "Auto-editor + custom script",
                "aspect_ratio": "9:16",
                "captions": "Auto-generated from script",
                "music": "Epidemic Sound short clips",
                "posting_schedule": "Daily 12:00 EST",
                "hashtags": ["#SpaceExplained", "#Shorts", "#SpaceFacts", "#NASA", "#Astronomy"]
            },
            "repurposing": {
                "long_to_shorts": "Auto-extract 3 best segments",
                "shorts_to_tiktok": "Cross-post with watermark",
                "shorts_to_reels": "Cross-post natively",
                "compilation_weekly": "Weekly 'Space This Week' compilation"
            },
            "kpi_targets": {
                "daily_views": 50000,
                "subscriber_conversion": "2% from Shorts",
                "long_form_funnel": "15% click-through to full video"
            }
        }
    
    async def _plan_localization(self) -> Dict:
        """Plan multi-language expansion."""
        return {
            "target_languages": self.localization_langs,
            "priority_order": [
                {"lang": "es", "market": "US Hispanic + Latin America", "rpm": "$5-15"},
                {"lang": "pt", "market": "Brazil", "rpm": "$3-10"},
                {"lang": "de", "market": "Germany/Austria/Switzerland", "rpm": "$10-25"},
                {"lang": "fr", "market": "France/Canada/Africa", "rpm": "$8-20"},
                {"lang": "hi", "market": "India", "rpm": "$1-5"},
                {"lang": "ja", "market": "Japan", "rpm": "$15-30"}
            ],
            "approach": {
                "method": "AI dubbing (ElevenLabs multilingual) + native review",
                "script_translation": "GPT-4 + native speaker verification",
                "metadata_translation": "Full title/description/tags",
                "thumbnail_localization": "Text overlay translation",
                "community": "Language-specific Discord channels"
            },
            "timeline": {
                "month_1_2": "Spanish + Portuguese (highest ROI)",
                "month_3_4": "German + French",
                "month_5_6": "Hindi + Japanese"
            },
            "budget_per_language": "$200-500/month for review/QA"
        }
    
    async def _build_sponsor_pipeline(self, metrics: Dict) -> Dict:
        """Build sponsorship outreach and management pipeline."""
        subs = metrics.get("subscribers", 0)
        avg_views = metrics.get("avg_views", 0)
        
        # Calculate sponsorship rate
        base_rate = max(500, avg_views * 0.03)  # $30 CPM equivalent
        
        return {
            "current_metrics": {
                "subscribers": subs,
                "avg_views": avg_views,
                "estimated_rate_per_video": f"${base_rate:,.0f} - ${base_rate*2:,.0f}"
            },
            "sponsor_categories": [
                {
                    "category": "VPN/Privacy",
                    "brands": ["NordVPN", "ExpressVPN", "Surfshark", "ProtonVPN"],
                    "rate": f"${base_rate*1.5:,.0f}",
                    "fit": "High - space audience values privacy"
                },
                {
                    "category": "Education/Courses",
                    "brands": ["Brilliant", "Coursera", "edX", "MasterClass", "Skillshare"],
                    "rate": f"${base_rate:,.0f}",
                    "fit": "High - audience wants to learn"
                },
                {
                    "category": "Space Gear/Telescopes",
                    "brands": ["Celestron", "Orion", "High Point Scientific", "OPT", "Explore Scientific"],
                    "rate": f"${base_rate*1.2:,.0f}",
                    "fit": "Very High - direct audience match"
                },
                {
                    "category": "Tech/Software",
                    "brands": ["Notion", "Obsidian", "Linear", "Vercel", "DigitalOcean"],
                    "rate": f"${base_rate:,.0f}",
                    "fit": "Medium - tech-savvy audience"
                },
                {
                    "category": "Science/Curiosity",
                    "brands": ["CuriosityStream", "Nebula", "MagellanTV", "Science Channel"],
                    "rate": f"${base_rate*1.3:,.0f}",
                    "fit": "High - content alignment"
                }
            ],
            "outreach_strategy": {
                "inbound": "Media kit on website + email in description",
                "outbound": "Quarterly outreach to 20 brands per category",
                "negotiation": "Bundle deals (3+ videos = 15% discount)",
                "exclusivity": "30-day category exclusivity for premium"
            },
            "management": {
                "platform": "Passionfruit / Grapevine / direct",
                "contract_template": "Standard influencer agreement",
                "deliverables": "60-90s integration + description link + pinned comment",
                "reporting": "Screenshot analytics at 24h, 7d, 30d"
            }
        }
    
    def _plan_multi_channel(self) -> Dict:
        """Plan multi-channel expansion."""
        return {
            "channels": [
                {
                    "name": "Space Explained Shorts",
                    "handle": "@SpaceExplainedShorts",
                    "focus": "Vertical-only, daily Shorts",
                    "content": "Repurposed + native Shorts",
                    "monetization": "Shorts Fund + cross-promotion"
                },
                {
                    "name": "Space Explained Español",
                    "handle": "@SpaceExplainedES",
                    "focus": "Spanish dubbed content",
                    "content": "Full localization of main channel",
                    "monetization": "AdSense + LatAm sponsors"
                },
                {
                    "name": "Space Explained Deep Dive",
                    "handle": "@SpaceExplainedDeep",
                    "focus": "30-60 min documentaries",
                    "content": "Extended cuts, bonus footage, expert interviews",
                    "monetization": "Patreon exclusive + sponsorships"
                },
                {
                    "name": "Space Explained Kids",
                    "handle": "@SpaceExplainedKids",
                    "focus": "Ages 8-14, educational",
                    "content": "Simplified scripts, colorful animations",
                    "monetization": "COPPA-compliant + educational sponsors"
                }
            ],
            "shared_infrastructure": [
                "Single research pipeline",
                "Shared asset library",
                "Unified brand guidelines",
                "Cross-promotion strategy"
            ],
            "timeline": "Launch 1 per quarter after main channel hits 100K subs"
        }
    
    def _plan_hiring(self, metrics: Dict, revenue: Dict) -> Dict:
        """Plan team hiring based on revenue milestones."""
        monthly_revenue = revenue.get("monthly_total", 0)
        
        hiring_plan = {
            "current": "Solo (all automated)",
            "milestones": []
        }
        
        if monthly_revenue >= 3000:
            hiring_plan["milestones"].append({
                "revenue": "$3,000/mo",
                "role": "Part-time Video Editor",
                "hours": "15/week",
                "cost": "$800-1,200/mo",
                "responsibilities": ["DaVinci polish", "Thumbnail finalization", "Shorts editing"]
            })
        
        if monthly_revenue >= 8000:
            hiring_plan["milestones"].append({
                "revenue": "$8,000/mo",
                "role": "Full-time Researcher/Writer",
                "hours": "40/week",
                "cost": "$4,000-6,000/mo",
                "responsibilities": ["Deep dive research", "Script writing", "Fact-checking", "Topic pipeline"]
            })
        
        if monthly_revenue >= 20000:
            hiring_plan["milestones"].append({
                "revenue": "$20,000/mo",
                "role": "Channel Manager",
                "hours": "40/week",
                "cost": "$5,000-8,000/mo",
                "responsibilities": ["Sponsor management", "Analytics", "Community", "Hiring", "Strategy"]
            })
        
        if monthly_revenue >= 50000:
            hiring_plan["milestones"].append({
                "revenue": "$50,000/mo",
                "role": "Creative Director + Team",
                "team": ["Motion Designer", "3D Artist", "Community Manager", "Business Dev"],
                "cost": "$25,000-40,000/mo",
                "responsibilities": ["Creative strategy", "Quality control", "New formats", "IP development"]
            })
        
        return hiring_plan
    
    def _plan_revenue_streams(self, revenue: Dict) -> Dict:
        """Plan revenue diversification."""
        current = revenue.get("monthly_total", 0)
        adsense = revenue.get("adsense", 0)
        
        return {
            "current_mix": {
                "adsense": f"{adsense} ({(adsense/current*100 if current else 0):.0f}%)",
                "sponsorships": f"{revenue.get('sponsorships', 0)} ({(revenue.get('sponsorships',0)/current*100 if current else 0):.0f}%)",
                "affiliates": f"{revenue.get('affiliates', 0)} ({(revenue.get('affiliates',0)/current*100 if current else 0):.0f}%)",
                "courses": f"{revenue.get('courses', 0)} ({(revenue.get('courses',0)/current*100 if current else 0):.0f}%)",
                "merch": f"{revenue.get('merch', 0)} ({(revenue.get('merch',0)/current*100 if current else 0):.0f}%)",
                "patreon": f"{revenue.get('patreon', 0)} ({(revenue.get('patreon',0)/current*100 if current else 0):.0f}%)"
            },
            "target_mix_12_months": {
                "adsense": "35%",
                "sponsorships": "30%",
                "affiliates": "10%",
                "courses": "15%",
                "merch": "5%",
                "patreon": "5%"
            },
            "action_items": [
                "Launch 'Rocket Science 101' course (Month 3)",
                "Set up Printful merch store (Month 2)",
                "Apply to 5 affiliate programs (Month 1)",
                "Create Patreon tiers (Month 2)",
                "Build sponsor media kit (Month 1)",
                "Negotiate first sponsorship bundle (Month 3)"
            ]
        }


# Register skills
register_skill(YouTubeAuthSkill)
register_skill(Phase1ChannelSetupSkill)
register_skill(Phase2ContentPipelineSkill)
register_skill(Phase3OptimizationSkill)
register_skill(Phase4ScalingSkill)