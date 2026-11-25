"""
Master Orchestrator - Coordinates all skills into complete automation pipeline.
Handles topic queue, scheduling, monitoring, and end-to-end production.
"""

import asyncio
import logging
import json
import yaml
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Set
from enum import Enum

from .registry import SkillRegistry, get_registry, BaseSkill, SkillCategory
from .pipeline import SkillPipeline, PipelineBuilder, PipelineStage, PipelineContext
from .context import SharedContext, ContextManager, ResourceManager, MemoryCache
from .modifier import ModifierFactory, ModifierChain
from .research_skill import NASASkill, SpaceNewsSkill, DeepDiveSkill
from .script_skill import ScriptSkill, TitleOptimizerSkill
from .vfx_skill import NASAFootageSkill, MotionGraphicsSkill, CompositingSkill, RIFEInterpolationSkill
from .voice_skill import ElevenLabsSkill, PronunciationSkill
from .youtube_automation_skill import (
    YouTubeAuthSkill, Phase1ChannelSetupSkill, 
    Phase2ContentPipelineSkill, Phase3OptimizationSkill, Phase4ScalingSkill
)


logger = logging.getLogger(__name__)


class OrchestrationMode(Enum):
    """Orchestration execution modes."""
    FULL_PIPELINE = "full_pipeline"           # End-to-end production
    RESEARCH_ONLY = "research_only"           # Research phase only
    PRODUCTION_ONLY = "production_only"       # Script → VFX → Voice → Upload
    UPLOAD_ONLY = "upload_only"               # Upload prepared content
    ANALYTICS_ONLY = "analytics_only"         # Optimization phase
    CONTINUOUS = "continuous"                  # Continuous automated operation


@dataclass
class Topic:
    """Content topic in the production queue."""
    id: str
    title: str
    pillar: str
    priority: int = 5
    video_type: str = "deep_dive"
    target_duration: int = 480
    tone: str = "educational"
    status: str = "queued"  # queued, researching, scripting, producing, ready, uploaded
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    scheduled_for: Optional[str] = None
    published_at: Optional[str] = None
    youtube_id: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    research_data: Dict[str, Any] = field(default_factory=dict)
    script_data: Dict[str, Any] = field(default_factory=dict)
    production_data: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductionJob:
    """Active production job."""
    job_id: str
    topic: Topic
    pipeline_context: PipelineContext
    started_at: str
    stage: PipelineStage
    progress: float = 0.0
    errors: List[str] = field(default_factory=list)


class SpaceExplorationOrchestrator:
    """Master orchestrator for Space Exploration channel automation."""
    
    def __init__(self, config_path: str = "config/orchestrator.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
        
        # Core infrastructure
        self.registry = get_registry()
        self.shared_context = SharedContext(
            cache=MemoryCache(max_size=2000),
            resource_manager=ResourceManager()
        )
        self.context_manager = ContextManager(self.shared_context)
        self.modifier_factory = ModifierFactory(
            cache_backend=self.shared_context.cache,
            resource_manager=self.shared_context.resource_manager
        )
        
        # State
        self.topic_queue: List[Topic] = []
        self.active_jobs: Dict[str, ProductionJob] = {}
        self.completed_jobs: List[ProductionJob] = []
        self.pipelines: Dict[str, SkillPipeline] = {}
        
        # YouTube service (initialized on demand)
        self.youtube_service = None
        
        # Setup skills
        self._register_skills()
        self._build_pipelines()
        
        # Load persistent state
        self._load_state()
    
    def _load_config(self) -> Dict:
        """Load orchestrator configuration."""
        if self.config_path.exists():
            with open(self.config_path) as f:
                return yaml.safe_load(f)
        
        # Default configuration
        return {
            "channel": {
                "name": "Space Explained",
                "handle": "@SpaceExplained",
                "description": "Your daily dose of space exploration, planetary science, and cosmic wonder.",
                "keywords": "space, nasa, astronomy, space exploration, planetary science, cosmology, exoplanets, rockets, spacex, artemis, mars, moon",
                "upload_schedule": {
                    "days": ["tuesday", "thursday", "saturday"],
                    "time": "18:00",
                    "timezone": "US/Eastern"
                },
                "content_pillars": [
                    "planetary_science",
                    "space_technology",
                    "cosmology", 
                    "exoplanets",
                    "missions",
                    "space_news"
                ],
                "playlists": [
                    {"title": "🚀 Space Missions & Launches", "description": "Live launches, mission updates, rocket science"},
                    {"title": "🌌 Deep Space & Cosmology", "description": "Black holes, galaxies, dark matter, universe origins"},
                    {"title": "🪐 Planetary Science", "description": "Mars, Venus, gas giants, moons, exoplanets"},
                    {"title": "🛰️ Space Technology", "description": "Rockets, satellites, stations, propulsion, robotics"},
                    {"title": "👨‍🚀 Astronaut Life & EVA", "description": "Spacewalks, ISS life, training, human spaceflight"},
                    {"title": "📰 Space News & Updates", "description": "Weekly space news, industry updates, policy"},
                    {"title": "🎬 Shorts: Quick Space Facts", "description": "60-second space facts, vertical format"}
                ]
            },
            "skills": {
                "nasa_research": {"nasa_api_key": "DEMO_KEY", "cache_ttl": 86400},
                "space_news": {"lookback_days": 7},
                "deep_dive": {"openai_api_key": "", "max_depth": 3},
                "script_writer": {"openai_api_key": "", "default_tone": "educational", "target_duration": 480},
                "title_optimizer": {"openai_api_key": ""},
                "nasa_footage": {"storage_path": "assets/nasa", "max_concurrent_downloads": 4},
                "motion_graphics": {"blender_path": "/usr/bin/blender", "template_library": "templates/blender"},
                "compositing": {"davinci_path": "/opt/resolve/bin/resolve"},
                "rife_interpolation": {"rife_model_path": "models/rife", "gpu_enabled": True},
                "elevenlabs_tts": {"api_key": "", "default_voice": "narrator", "cache_dir": "cache/voice"},
                "pronunciation_manager": {"dictionary_path": "config/pronunciation.json"},
                "youtube_auth": {"client_secrets_file": "config/youtube_client_secrets.json", "token_file": "config/youtube_token.json"},
                "phase1_channel_setup": {"channel_config": {}, "branding_assets_dir": "assets/branding"},
                "phase2_content_pipeline": {"upload_schedule": {}, "content_pillars": []},
                "phase3_optimization": {"analytics_api": "", "testing_config": {}},
                "phase4_scaling": {"scaling_config": {}}
            },
            "quality": {
                "min_script_score": 0.8,
                "min_visual_quality": 0.7,
                "min_audio_quality": 0.8,
                "require_manual_review": True
            },
            "paths": {
                "assets": "assets",
                "output": "output",
                "cache": "cache",
                "logs": "logs",
                "scripts": "scripts",
                "templates": "templates"
            }
        }
    
    def _register_skills(self):
        """Register all skills with configurations."""
        skill_configs = self.config.get("skills", {})
        
        # Register each skill with its config
        skill_classes = [
            NASASkill, SpaceNewsSkill, DeepDiveSkill,
            ScriptSkill, TitleOptimizerSkill,
            NASAFootageSkill, MotionGraphicsSkill, CompositingSkill, RIFEInterpolationSkill,
            ElevenLabsSkill, PronunciationSkill,
            YouTubeAuthSkill, Phase1ChannelSetupSkill, 
            Phase2ContentPipelineSkill, Phase3OptimizationSkill, Phase4ScalingSkill
        ]
        
        for skill_class in skill_classes:
            if hasattr(skill_class, 'metadata'):
                config = skill_configs.get(skill_class.metadata.name, {})
                self.registry.register(skill_class, config=config)
    
    def _build_pipelines(self):
        """Build standard pipelines for different modes."""
        
        # Research pipeline
        research_pipeline = PipelineBuilder("research", self.registry)\
            .add_skills(["nasa_research", "space_news", "deep_dive"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["research"] = research_pipeline
        
        # Script pipeline
        script_pipeline = PipelineBuilder("script", self.registry)\
            .add_skills(["script_writer", "title_optimizer"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["script"] = script_pipeline
        
        # VFX pipeline
        vfx_pipeline = PipelineBuilder("vfx", self.registry)\
            .add_skills(["nasa_footage", "motion_graphics", "compositing", "rife_interpolation"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["vfx"] = vfx_pipeline
        
        # Voice pipeline
        voice_pipeline = PipelineBuilder("voice", self.registry)\
            .add_skills(["elevenlabs_tts", "pronunciation_manager"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["voice"] = voice_pipeline
        
        # Full production pipeline
        production_pipeline = PipelineBuilder("production", self.registry)\
            .add_skills([
                "nasa_research", "space_news", "deep_dive",
                "script_writer", "title_optimizer",
                "nasa_footage", "motion_graphics", "compositing", "rife_interpolation",
                "elevenlabs_tts",
                "youtube_auth"
            ])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["production"] = production_pipeline
        
        # Phase pipelines
        phase1_pipeline = PipelineBuilder("phase1", self.registry)\
            .add_skills(["youtube_auth", "phase1_channel_setup"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["phase1"] = phase1_pipeline
        
        phase2_pipeline = PipelineBuilder("phase2", self.registry)\
            .add_skills(["phase2_content_pipeline"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["phase2"] = phase2_pipeline
        
        phase3_pipeline = PipelineBuilder("phase3", self.registry)\
            .add_skills(["phase3_optimization"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["phase3"] = phase3_pipeline
        
        phase4_pipeline = PipelineBuilder("phase4", self.registry)\
            .add_skills(["phase4_scaling"])\
            .with_config(self.config.get("skills", {}))\
            .build()
        self.pipelines["phase4"] = phase4_pipeline
    
    def _load_state(self):
        """Load persistent state from disk."""
        state_dir = Path("state")
        state_dir.mkdir(exist_ok=True)
        
        # Load topic queue
        queue_file = state_dir / "topic_queue.json"
        if queue_file.exists():
            with open(queue_file) as f:
                data = json.load(f)
                self.topic_queue = [Topic(**item) for item in data]
        
        # Load completed jobs
        jobs_file = state_dir / "completed_jobs.json"
        if jobs_file.exists():
            with open(jobs_file) as f:
                data = json.load(f)
                self.completed_jobs = [ProductionJob(**item) for item in data]
    
    def _save_state(self):
        """Save persistent state to disk."""
        state_dir = Path("state")
        state_dir.mkdir(exist_ok=True)
        
        # Save topic queue
        queue_file = state_dir / "topic_queue.json"
        with open(queue_file, 'w') as f:
            json.dump([{
                "id": t.id, "title": t.title, "pillar": t.pillar,
                "priority": t.priority, "video_type": t.video_type,
                "target_duration": t.target_duration, "tone": t.tone,
                "status": t.status, "created_at": t.created_at,
                "scheduled_for": t.scheduled_for, "published_at": t.published_at,
                "youtube_id": t.youtube_id, "metadata": t.metadata,
                "research_data": t.research_data, "script_data": t.script_data,
                "production_data": t.production_data
            } for t in self.topic_queue], f, indent=2)
        
        # Save completed jobs
        jobs_file = state_dir / "completed_jobs.json"
        with open(jobs_file, 'w') as f:
            json.dump([{
                "job_id": j.job_id, "topic_id": j.topic.id,
                "started_at": j.started_at, "stage": j.stage.value,
                "progress": j.progress, "errors": j.errors
            } for j in self.completed_jobs], f, indent=2)
    
    # ========================================================================
    # Public API
    # ========================================================================
    
    async def run_full_pipeline(self, topic: Topic) -> Dict[str, Any]:
        """Run complete production pipeline for a topic."""
        job_id = str(uuid.uuid4())[:8]
        
        # Create pipeline context
        pipeline_context = PipelineContext(
            pipeline_id=job_id,
            topic_id=topic.id,
            topic_data=topic.__dict__
        )
        
        # Create job
        job = ProductionJob(
            job_id=job_id,
            topic=topic,
            pipeline_context=pipeline_context,
            started_at=datetime.now().isoformat(),
            stage=PipelineStage.INIT
        )
        
        self.active_jobs[job_id] = job
        topic.status = "producing"
        self._save_state()
        
        try:
            # Run production pipeline
            result = await self.pipelines["production"].execute(
                topic_id=topic.id,
                topic_data=topic.__dict__
            )
            
            # Update topic with results
            topic.status = "ready"
            topic.research_data = result.get("nasa_research", {})
            topic.research_data.update(result.get("space_news", {}))
            topic.research_data.update(result.get("deep_dive", {}))
            topic.script_data = result.get("script", {})
            topic.production_data = result.get("compositing", {})
            
            # Upload to YouTube
            upload_result = await self._upload_to_youtube(topic, result)
            topic.youtube_id = upload_result.get("video_id")
            topic.published_at = datetime.now().isoformat()
            topic.status = "uploaded"
            
            job.stage = PipelineStage.COMPLETE
            job.progress = 1.0
            
            self._save_state()
            
            return {
                "success": True,
                "job_id": job_id,
                "topic_id": topic.id,
                "youtube_id": topic.youtube_id,
                "result": result
            }
            
        except Exception as e:
            logger.exception(f"Pipeline failed for {topic.id}")
            topic.status = "failed"
            job.stage = PipelineStage.FAILED
            job.errors.append(str(e))
            self._save_state()
            return {"success": False, "job_id": job_id, "error": str(e)}
        
        finally:
            self.active_jobs.pop(job_id, None)
            self.completed_jobs.append(job)
    
    async def run_research_only(self, topic: Topic) -> Dict[str, Any]:
        """Run only research phase."""
        result = await self.pipelines["research"].execute(
            topic_id=topic.id,
            topic_data=topic.__dict__
        )
        
        topic.research_data = result
        topic.status = "researched"
        self._save_state()
        
        return result
    
    async def run_script_only(self, topic: Topic) -> Dict[str, Any]:
        """Run only script phase (requires research data)."""
        # Prepare context with research data
        context_data = topic.__dict__.copy()
        context_data["research_data"] = topic.research_data
        
        result = await self.pipelines["script"].execute(
            topic_id=topic.id,
            topic_data=context_data
        )
        
        topic.script_data = result
        topic.status = "scripted"
        self._save_state()
        
        return result
    
    async def run_production_only(self, topic: Topic) -> Dict[str, Any]:
        """Run VFX + Voice production (requires script)."""
        context_data = topic.__dict__.copy()
        context_data["script"] = topic.script_data
        context_data["research_data"] = topic.research_data
        
        # Run VFX
        vfx_result = await self.pipelines["vfx"].execute(
            topic_id=topic.id,
            topic_data=context_data
        )
        
        # Run Voice
        voice_result = await self.pipelines["voice"].execute(
            topic_id=topic.id,
            topic_data={"script": topic.script_data}
        )
        
        topic.production_data = {**vfx_result, **voice_result}
        topic.status = "produced"
        self._save_state()
        
        return {**vfx_result, **voice_result}
    
    async def upload_prepared(self, topic: Topic) -> Dict[str, Any]:
        """Upload already prepared video."""
        if not topic.production_data.get("final_render"):
            return {"success": False, "error": "No final render available"}
        
        result = await self._upload_to_youtube(topic, topic.production_data)
        
        topic.youtube_id = result.get("video_id")
        topic.published_at = datetime.now().isoformat()
        topic.status = "uploaded"
        self._save_state()
        
        return result
    
    async def run_analytics_optimization(self) -> Dict[str, Any]:
        """Run Phase 3 optimization analysis."""
        # Get recent videos
        recent_videos = await self._get_recent_videos()
        
        result = await self.pipelines["phase3"].execute(
            topic_id="analytics_batch",
            topic_data={"published_videos": recent_videos}
        )
        
        return result
    
    async def run_daily_batch(self, max_videos: int = 3) -> Dict[str, Any]:
        """Run daily production batch."""
        # Select topics ready for production
        ready_topics = [t for t in self.topic_queue if t.status in ["queued", "researched", "scripted"]]
        ready_topics.sort(key=lambda t: (-t.priority, t.created_at))
        
        selected = ready_topics[:max_videos]
        
        results = {
            "started": [],
            "completed": [],
            "failed": []
        }
        
        for topic in selected:
            # Run appropriate pipeline stage
            if topic.status == "queued":
                await self.run_research_only(topic)
                await self.run_script_only(topic)
            
            elif topic.status == "researched":
                await self.run_script_only(topic)
            
            elif topic.status == "scripted":
                pass  # Ready for production
            
            # Run production
            result = await self.run_full_pipeline(topic)
            
            if result.get("success"):
                results["completed"].append(result)
            else:
                results["failed"].append(result)
            
            results["started"].append(topic.id)
        
        return results
    
    async def run_continuous(self, interval_hours: int = 24):
        """Run continuous automation loop."""
        logger.info(f"Starting continuous mode, interval: {interval_hours}h")
        
        while True:
            try:
                # Daily batch
                await self.run_daily_batch()
                
                # Weekly analytics (every 7 days)
                if datetime.now().weekday() == 0:  # Monday
                    await self.run_analytics_optimization()
                
                # Save state
                self._save_state()
                
            except Exception as e:
                logger.error(f"Continuous loop error: {e}")
            
            # Wait for next interval
            await asyncio.sleep(interval_hours * 3600)
    
    # ========================================================================
    # Topic Queue Management
    # ========================================================================
    
    def add_topic(self, topic: Topic) -> str:
        """Add topic to production queue."""
        self.topic_queue.append(topic)
        self.topic_queue.sort(key=lambda t: (-t.priority, t.created_at))
        self._save_state()
        return topic.id
    
    def add_topics(self, topics: List[Topic]) -> List[str]:
        """Add multiple topics."""
        ids = []
        for topic in topics:
            ids.append(self.add_topic(topic))
        return ids
    
    def get_next_topics(self, count: int = 5) -> List[Topic]:
        """Get next topics for production."""
        ready = [t for t in self.topic_queue if t.status in ["queued", "researched", "scripted"]]
        ready.sort(key=lambda t: (-t.priority, t.created_at))
        return ready[:count]
    
    def get_topic(self, topic_id: str) -> Optional[Topic]:
        """Get topic by ID."""
        for topic in self.topic_queue:
            if topic.id == topic_id:
                return topic
        return None
    
    def update_topic_status(self, topic_id: str, status: str):
        """Update topic status."""
        topic = self.get_topic(topic_id)
        if topic:
            topic.status = status
            self._save_state()
    
    def remove_topic(self, topic_id: str) -> bool:
        """Remove topic from queue."""
        self.topic_queue = [t for t in self.topic_queue if t.id != topic_id]
        self._save_state()
        return True
    
    # ========================================================================
    # YouTube Integration
    # ========================================================================
    
    async def _get_youtube_service(self):
        """Get authenticated YouTube service."""
        if self.youtube_service is None:
            auth_skill = YouTubeAuthSkill(self.config.get("skills", {}).get("youtube_auth", {}))
            context = self.context_manager.create_context("youtube_auth", {})
            result = await auth_skill.execute(context)
            self.youtube_service = result.get("youtube_service")
        return self.youtube_service
    
    async def _upload_to_youtube(self, topic: Topic, production_data: Dict) -> Dict:
        """Upload video to YouTube."""
        service = await self._get_youtube_service()
        
        video_path = production_data.get("final_render") or production_data.get("compositing", {}).get("final_render")
        if not video_path or not Path(video_path).exists():
            return {"success": False, "error": "Video file not found"}
        
        # Build metadata
        script_data = topic.script_data
        metadata = VideoMetadata(
            title=script_data.get("title", topic.title),
            description=script_data.get("description", ""),
            tags=script_data.get("tags", []),
            publish_at=topic.scheduled_for
        )
        
        # Upload
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')
        
        request = service.videos().insert(
            part="snippet,status,recordingDetails",
            body={
                "snippet": {
                    "title": metadata.title,
                    "description": metadata.description,
                    "tags": metadata.tags,
                    "categoryId": metadata.category_id,
                    "defaultLanguage": metadata.default_language
                },
                "status": {
                    "privacyStatus": metadata.privacy_status,
                    "publishAt": metadata.publish_at,
                    "selfDeclaredMadeForKids": metadata.made_for_kids
                },
                "recordingDetails": {
                    "locationDescription": metadata.location,
                    "recordingDate": metadata.recording_date or datetime.now().isoformat()
                }
            },
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Upload progress: {int(status.progress() * 100)}%")
        
        video_id = response['id']
        
        # Upload thumbnail
        thumbnails = production_data.get("thumbnails", [])
        if thumbnails:
            service.thumbnails().set(
                videoId=video_id,
                media_body=MediaFileUpload(thumbnails[0], mimetype='image/jpeg')
            ).execute()
        
        return {"success": True, "video_id": video_id, "url": f"https://youtube.com/watch?v={video_id}"}
    
    async def _get_recent_videos(self, days: int = 30) -> List[Dict]:
        """Get recent videos from channel."""
        service = await self._get_youtube_service()
        
        try:
            request = service.search().list(
                part="snippet",
                forMine=True,
                type="video",
                order="date",
                maxResults=50
            )
            response = request.execute()
            
            videos = []
            for item in response.get("items", []):
                video_id = item["id"]["videoId"]
                # Get analytics for each
                analytics = await self._get_video_analytics(service, video_id)
                videos.append({
                    "video_id": video_id,
                    "title": item["snippet"]["title"],
                    "published": item["snippet"]["publishedAt"],
                    "thumbnail_variants": [],  # Would need to track separately
                    "analytics": analytics
                })
            
            return videos
        except Exception as e:
            logger.error(f"Failed to get recent videos: {e}")
            return []
    
    async def _get_video_analytics(self, service, video_id: str) -> Dict:
        """Get analytics for a video."""
        try:
            request = service.videos().list(
                part="statistics,contentDetails",
                id=video_id
            )
            response = request.execute()
            
            if response.get("items"):
                stats = response["items"][0]["statistics"]
                return {
                    "views": int(stats.get("viewCount", 0)),
                    "likes": int(stats.get("likeCount", 0)),
                    "comments": int(stats.get("commentCount", 0)),
                    "duration": response["items"][0]["contentDetails"]["duration"]
                }
        except Exception:
            pass
        
        return {}
    
    # ========================================================================
    # Status & Monitoring
    # ========================================================================
    
    def get_status(self) -> Dict[str, Any]:
        """Get orchestrator status."""
        status_counts = {}
        for topic in self.topic_queue:
            status_counts[topic.status] = status_counts.get(topic.status, 0) + 1
        
        return {
            "topic_queue": {
                "total": len(self.topic_queue),
                "by_status": status_counts,
                "next_5": [
                    {"id": t.id, "title": t.title, "status": t.status, "priority": t.priority}
                    for t in self.get_next_topics(5)
                ]
            },
            "active_jobs": len(self.active_jobs),
            "completed_jobs": len(self.completed_jobs),
            "pipelines": list(self.pipelines.keys()),
            "youtube_connected": self.youtube_service is not None
        }
    
    def get_topic_queue(self) -> List[Dict]:
        """Get full topic queue."""
        return [
            {
                "id": t.id,
                "title": t.title,
                "pillar": t.pillar,
                "priority": t.priority,
                "status": t.status,
                "created_at": t.created_at,
                "scheduled_for": t.scheduled_for,
                "youtube_id": t.youtube_id
            }
            for t in self.topic_queue
        ]


# Convenience functions for CLI usage

async def create_orchestrator(config_path: str = "config/orchestrator.yaml") -> SpaceExplorationOrchestrator:
    """Create and initialize orchestrator."""
    orchestrator = SpaceExplorationOrchestrator(config_path)
    return orchestrator


async def run_daily_production(orchestrator: SpaceExplorationOrchestrator, max_videos: int = 3):
    """Run daily production batch."""
    return await orchestrator.run_daily_batch(max_videos)


async def run_continuous_automation(orchestrator: SpaceExplorationOrchestrator, interval_hours: int = 24):
    """Run continuous automation."""
    await orchestrator.run_continuous(interval_hours)


# CLI entry point
if __name__ == "__main__":
    import sys
    
    async def main():
        orchestrator = await create_orchestrator()
        
        if len(sys.argv) > 1:
            command = sys.argv[1]
            
            if command == "status":
                print(json.dumps(orchestrator.get_status(), indent=2))
            
            elif command == "queue":
                print(json.dumps(orchestrator.get_topic_queue(), indent=2))
            
            elif command == "daily":
                result = await orchestrator.run_daily_batch()
                print(json.dumps(result, indent=2))
            
            elif command == "continuous":
                await orchestrator.run_continuous()
            
            elif command == "analytics":
                result = await orchestrator.run_analytics_optimization()
                print(json.dumps(result, indent=2))
            
            else:
                print(f"Unknown command: {command}")
        else:
            print("Space Exploration Orchestrator")
            print("Commands: status, queue, daily, continuous, analytics")
    
    asyncio.run(main())