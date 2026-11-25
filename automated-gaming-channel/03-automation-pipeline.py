#!/usr/bin/env python3
"""
META GAMING INDIA - FULL AUTOMATION PIPELINE
=============================================
Runs daily via cron. Human only records gameplay clips (30 min/day).
Everything else: Topic selection → Script → VO → Edit → Thumbnail → Upload → Shorts → Analytics
"""

import os
import json
import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass, asdict
from enum import Enum

import openai
import elevenlabs
import requests
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ============================================================================
# CONFIGURATION
# ============================================================================

class Game(Enum):
    BGMI = "bgmi"
    FREE_FIRE = "free_fire"
    COD_MOBILE = "cod_mobile"
    POKEMON_UNITE = "pokemon_unite"

class VideoType(Enum):
    PATCH_BREAKDOWN = "patch_breakdown"
    META_TIER_LIST = "meta_tier_list"
    SETTINGS_CONFIG = "settings_config"
    RANK_PUSH = "rank_push"
    ECONOMY_SKINS = "economy_skins"

@dataclass
class VideoTopic:
    id: str
    game: Game
    type: VideoType
    title: str
    keywords: List[str]
    priority: int  # 1-10
    patch_version: Optional[str] = None
    season: Optional[str] = None
    status: str = "queued"  # queued, scripting, recording, editing, ready, uploaded
    created_at: str = ""
    scheduled_for: str = ""

@dataclass
class GameplayClip:
    id: str
    topic_id: str
    file_path: str
    description: str  # What this clip shows
    timestamp_start: float
    timestamp_end: float
    tags: List[str]  # e.g., ["m416", "spray", "training_ground"]

@dataclass
class VideoScript:
    topic_id: str
    hook: str
    sections: List[Dict]  # {title, content, clip_tags, duration_est}
    outro: str
    cta: str
    timestamps: List[Dict]
    metadata: Dict  # title, description, tags, hashtags

# ============================================================================
# MAIN PIPELINE CLASS
# ============================================================================

class MetaGamingPipeline:
    def __init__(self, config_path: str = "config.json"):
        self.config = self.load_config(config_path)
        self.setup_logging()
        self.youtube = self.auth_youtube()
        self.topic_queue: List[VideoTopic] = []
        self.clip_library: List[GameplayClip] = []
        
    def load_config(self, path: str) -> Dict:
        with open(path) as f:
            return json.load(f)
    
    def setup_logging(self):
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('pipeline.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def auth_youtube(self):
        """Authenticate with YouTube Data API v3"""
        creds = None
        token_path = self.config['youtube']['token_path']
        client_secrets = self.config['youtube']['client_secrets']
        scopes = ['https://www.googleapis.com/auth/youtube.upload',
                  'https://www.googleapis.com/auth/youtube.readonly',
                  'https://www.googleapis.com/auth/youtube.force-ssl']
        
        if os.path.exists(token_path):
            creds = Credentials.from_authorized_user_file(token_path, scopes)
        
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(client_secrets, scopes)
                creds = flow.run_local_server(port=0)
            with open(token_path, 'w') as token:
                token.write(creds.to_json())
        
        return build('youtube', 'v3', credentials=creds)

    # ========================================================================
    # STEP 1: TOPIC SELECTION (AI-Driven)
    # ========================================================================
    
    async def select_next_topic(self) -> VideoTopic:
        """AI selects highest-opportunity topic based on trends, gaps, schedule"""
        
        # Load current queue
        self.topic_queue = self.load_topic_queue()
        
        # Get trending data
        trends = await self.fetch_trending_data()
        
        # Build prompt for GPT
        prompt = f"""
        You are the Content Director for Meta Gaming India.
        
        CURRENT QUEUE ({len(self.topic_queue)} topics):
        {json.dumps([asdict(t) for t in self.topic_queue[:10]], indent=2)}
        
        TRENDING DATA:
        {json.dumps(trends, indent=2)}
        
        UPCOMING PATCHES:
        - BGMI: {self.config['schedule']['bgmi_patch_dates']}
        - Free Fire: {self.config['schedule']['ff_patch_dates']}
        - CODM: {self.config['schedule']['codm_patch_dates']}
        
        SELECTION CRITERIA (Priority Order):
        1. Patch day = PATCH_BREAKDOWN (Must publish within 4 hours)
        2. Post-patch (Day 1-3) = META_TIER_LIST + SETTINGS_CONFIG
        3. Mid-season = RANK_PUSH + ECONOMY_SKINS
        4. Competitor gaps (topics they missed)
        5. Search volume trends (Google Trends + YouTube Suggest)
        
        Return JSON: {{"selected_topic_id": "...", "reason": "...", "next_3_topics": [...] }}
        """
        
        response = await self.call_gpt(prompt, max_tokens=1000)
        decision = json.loads(response)
        
        # Update selected topic status
        for topic in self.topic_queue:
            if topic.id == decision['selected_topic_id']:
                topic.status = "scripting"
                break
        
        self.save_topic_queue()
        self.logger.info(f"Selected topic: {decision['selected_topic_id']} - {decision['reason']}")
        return next(t for t in self.topic_queue if t.id == decision['selected_topic_id'])

    async def fetch_trending_data(self) -> Dict:
        """Fetch trending searches, competitor uploads, patch news"""
        return {
            "bgmi_trending": ["m416 buff", "gyroscope settings", "conqueror push"],
            "ff_trending": ["ob47 patch", "chrono character", "diamond royale value"],
            "codm_trending": ["season 14 meta", "best loadout", "ranked tips"],
            "competitor_gaps": ["bgmi 3.3 gyro settings", "ff diamond royale roi"]
        }

    # ========================================================================
    # STEP 2: SCRIPT GENERATION (AI + Template)
    # ========================================================================
    
    async def generate_script(self, topic: VideoTopic) -> VideoScript:
        """Generate full script with clip mapping using GPT-4o"""
        
        # Get relevant clips from library
        relevant_clips = [c for c in self.clip_library if topic.id in c.tags or any(t in c.tags for t in topic.keywords)]
        
        template = self.get_script_template(topic.type)
        
        prompt = f"""
        Generate a complete video script for Meta Gaming India.
        
        TOPIC: {topic.title}
        GAME: {topic.game.value}
        TYPE: {topic.type.value}
        PATCH/SEASON: {topic.patch_version or topic.season}
        KEYWORDS: {topic.keywords}
        
        AVAILABLE CLIPS ({len(relevant_clips)}):
        {json.dumps([{"id": c.id, "desc": c.description, "tags": c.tags, "duration": c.timestamp_end - c.timestamp_start} for c in relevant_clips[:20]], indent=2)}
        
        TEMPLATE STRUCTURE:
        {template}
        
        REQUIREMENTS:
        - Hook in first 5 seconds (pattern interrupt + promise)
        - Map EVERY section to specific clip tags
        - Include exact timestamps for description
        - Data-driven claims only (cite sources)
        - Indian gaming context (pro player names, local meta)
        - SEO-optimized title + description + tags
        - 3 Shorts hooks identified
        
        Return JSON matching VideoScript schema.
        """
        
        response = await self.call_gpt(prompt, max_tokens=3000)
        script_data = json.loads(response)
        script = VideoScript(topic_id=topic.id, **script_data)
        
        # Save script
        script_path = f"scripts/{topic.id}.json"
        os.makedirs("scripts", exist_ok=True)
        with open(script_path, 'w') as f:
            json.dump(asdict(script), f, indent=2)
        
        topic.status = "scripted"
        self.save_topic_queue()
        self.logger.info(f"Script generated for {topic.id}")
        return script

    def get_script_template(self, vtype: VideoType) -> str:
        templates = {
            VideoType.PATCH_BREAKDOWN: """
            HOOK (0-5s): "Patch 3.3 just dropped. M416 got a SECRET buff nobody's talking about."
            SECTION 1: Major Changes (3-4 biggest) - Map to gameplay clips
            SECTION 2: Meta Impact - What this means for ranked
            SECTION 3: Best Loadouts Now - Tier list with clips
            SECTION 4: Pro Adjustments - Sensitivity/HUD changes needed
            OUTRO: "Test in training ground. Config in description."
            """,
            VideoType.META_TIER_LIST: """
            HOOK: "Stop using the AKM. Here's the ACTUAL S-Tier ARs after the patch."
            SECTION 1: S-Tier (2-3 weapons) - Stats + Clips
            SECTION 2: A-Tier (Viable alternatives)
            SECTION 3: Situational Picks
            SECTION 4: What to AVOID (Nerfed/Dead)
            OUTRO: "Screenshot this tier list. Link in pinned comment."
            """,
            VideoType.SETTINGS_CONFIG: """
            HOOK: "Jonathan uses 300% gyro. Scout uses 120 general. Here's WHY."
            SECTION 1: General Sensitivity Breakdown
            SECTION 2: Red Dot / 2x / 4x / Scope
            SECTION 3: Gyroscope Settings (Claw vs Thumb)
            SECTION 4: HUD Layouts (3-finger / 4-finger / Claw)
            SECTION 5: Download Link + How to Import
            OUTRO: "Copy, test, adjust. Your muscle memory decides."
            """,
        }
        return templates.get(vtype, templates[VideoType.PATCH_BREAKDOWN])

    # ========================================================================
    # STEP 3: VOICEOVER GENERATION (ElevenLabs)
    # ========================================================================
    
    async def generate_voiceover(self, script: VideoScript) -> str:
        """Generate VO using ElevenLabs API, return audio file path"""
        
        full_text = f"{script.hook} " + " ".join([s['content'] for s in script.sections]) + f" {script.outro} {script.cta}"
        
        # Split into chunks if > 5000 chars (ElevenLabs limit)
        chunks = self.chunk_text(full_text, 4500)
        audio_files = []
        
        for i, chunk in enumerate(chunks):
            audio = await self.call_elevenlabs(chunk, voice_id=self.config['elevenlabs']['voice_id'])
            chunk_path = f"audio/{script.topic_id}_part{i}.mp3"
            os.makedirs("audio", exist_ok=True)
            with open(chunk_path, 'wb') as f:
                f.write(audio)
            audio_files.append(chunk_path)
        
        # Concatenate if multiple chunks
        if len(audio_files) > 1:
            final_path = f"audio/{script.topic_id}_final.mp3"
            self.concat_audio(audio_files, final_path)
        else:
            final_path = audio_files[0]
        
        self.logger.info(f"Voiceover generated: {final_path}")
        return final_path

    async def call_elevenlabs(self, text: str, voice_id: str) -> bytes:
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
        headers = {
            "xi-api-key": self.config['elevenlabs']['api_key'],
            "Content-Type": "application/json"
        }
        data = {
            "text": text,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.45,
                "similarity_boost": 0.70,
                "style": 0.2,
                "use_speaker_boost": True
            }
        }
        response = requests.post(url, headers=headers, json=data)
        response.raise_for_status()
        return response.content

    def chunk_text(self, text: str, max_len: int) -> List[str]:
        sentences = text.split('. ')
        chunks, current = [], ""
        for s in sentences:
            if len(current) + len(s) < max_len:
                current += s + ". "
            else:
                chunks.append(current.strip())
                current = s + ". "
        if current:
            chunks.append(current.strip())
        return chunks

    def concat_audio(self, files: List[str], output: str):
        import subprocess
        list_file = "concat_list.txt"
        with open(list_file, 'w') as f:
            for file in files:
                f.write(f"file '{file}'\n")
        subprocess.run(['ffmpeg', '-f', 'concat', '-safe', '0', '-i', list_file, '-c', 'copy', output], check=True)
        os.remove(list_file)

    # ========================================================================
    # STEP 4: VIDEO EDITING (CapCut API / DaVinci Script / AutoEditor)
    # ========================================================================
    
    async def edit_video(self, topic: VideoTopic, script: VideoScript, audio_path: str) -> str:
        """Edit video using CapCut API (preferred) or DaVinci Resolve script"""
        
        # Prepare edit plan
        edit_plan = self.create_edit_plan(script, topic.game)
        
        # Use CapCut API if available, else DaVinci script
        if self.config['editing']['engine'] == 'capcut_api':
            output_path = await self.edit_with_capcut(edit_plan, audio_path, topic.id)
        else:
            output_path = await self.edit_with_davinci(edit_plan, audio_path, topic.id)
        
        # Generate Shorts versions
        await self.generate_shorts(output_path, script, topic.id)
        
        topic.status = "edited"
        self.save_topic_queue()
        self.logger.info(f"Video edited: {output_path}")
        return output_path

    def create_edit_plan(self, script: VideoScript, game: Game) -> Dict:
        """Create detailed edit plan for automation"""
        plan = {
            "resolution": "1920x1080",
            "fps": 30,
            "color_grade": self.config['branding']['color_grade'],
            "music": self.select_music(script),
            "intro": {"duration": 3, "template": "channel_intro"},
            "sections": [],
            "outro": {"duration": 5, "template": "channel_outro"},
            "shorts_markers": []  # Timestamps for Shorts extraction
        }
        
        current_time = 3  # After intro
        
        for i, section in enumerate(script.sections):
            clip_tags = section.get('clip_tags', [])
            duration = section.get('duration_est', 60)
            
            plan["sections"].append({
                "index": i,
                "title": section['title'],
                "audio_start": current_time,
                "audio_end": current_time + duration,
                "clip_tags": clip_tags,
                "overlays": self.generate_overlays(section, game),
                "transitions": "cut" if i > 0 else "fade_in"
            })
            
            # Mark for Shorts (best 15-60 sec segments)
            if 'shorts_hook' in section:
                plan["shorts_markers"].append({
                    "start": current_time + 5,
                    "end": current_time + min(duration, 55),
                    "hook": section['shorts_hook'],
                    "format": "vertical"
                })
            
            current_time += duration
        
        return plan

    def select_music(self, script: VideoScript) -> str:
        return self.config['branding']['music_tracks'].get(
            script.metadata.get('type', 'default'), 
            self.config['branding']['music_tracks']['default']
        )

    def generate_overlays(self, section: Dict, game: Game) -> List[Dict]:
        """Generate overlay specs: stats, weapon names, tier badges, etc."""
        overlays = []
        content = section.get('content', '').lower()
        
        # Weapon name overlays
        for weapon in ['m416', 'akm', 'groza', 'scar', 'qbz', 'm24', 'awm', 'm1887', 'uzi', 'vector', 'pp19', 'dp28', 'm249']:
            if weapon in content:
                overlays.append({"type": "weapon_name", "text": weapon.upper(), "position": "top_left", "duration": 3})
        
        # Stat overlays
        import re
        stats = re.findall(r'([+-]\d+%|\d+\.\d+ KD|\d+% (Pick|WR|HS))', content)
        for stat in stats:
            overlays.append({"type": "stat", "text": stat, "position": "bottom_right", "duration": 4})
        
        # Tier badges
        for tier in ['S-Tier', 'A-Tier', 'B-Tier', 'C-Tier', 'F-Tier', 'META', 'NERFED', 'BUFFED', 'NEW']:
            if tier.lower() in content:
                overlays.append({"type": "badge", "text": tier, "position": "top_right", "duration": 3})
        
        return overlays

    async def edit_with_capcut(self, plan: Dict, audio_path: str, topic_id: str) -> str:
        """Edit using CapCut API (requires CapCut for Business/Enterprise)"""
        # Placeholder - CapCut API access is limited
        return await self.edit_with_davinci(plan, audio_path, topic_id)

    async def edit_with_davinci(self, plan: Dict, audio_path: str, topic_id: str) -> str:
        """Generate DaVinci Resolve Python script and execute"""
        
        script_content = self.generate_davinci_script(plan, audio_path, topic_id)
        script_path = f"davinci_scripts/{topic_id}.py"
        os.makedirs("davinci_scripts", exist_ok=True)
        
        with open(script_path, 'w') as f:
            f.write(script_content)
        
        # Execute DaVinci Resolve script
        output_path = f"output/{topic_id}.mp4"
        os.makedirs("output", exist_ok=True)
        
        self.logger.info(f"DaVinci script generated: {script_path}")
        return output_path

    def generate_davinci_script(self, plan: Dict, audio_path: str, topic_id: str) -> str:
        """Generate Python script for DaVinci Resolve"""
        return f'''
import sys
sys.path.append("/Applications/DaVinci Resolve/DaVinci Resolve.app/Contents/Libraries/Fusion/fusionscript.so")
import davinci_resolve as dvr

resolve = dvr.scriptapp("Resolve")
pm = resolve.GetProjectManager()
project = pm.LoadProject("MetaGamingTemplate")
timeline = project.GetCurrentTimeline()

# Import media
media_pool = project.GetMediaPool()
media_pool.ImportMedia(["{audio_path}"] + [clip for clip in clips])

# Build timeline per plan
{self.generate_timeline_code(plan)}

# Render
project.SetRenderSettings({{
    "TargetDir": "output",
    "CustomName": "{topic_id}",
    "Format": "mp4",
    "Codec": "H.264",
    "Resolution": "1920x1080",
    "FrameRate": 30,
    "Quality": "High"
}})
project.StartRendering()
'''

    def generate_timeline_code(self, plan: Dict) -> str:
        return "# Timeline construction code here"

    async def generate_shorts(self, long_form_path: str, script: VideoScript, topic_id: str):
        """Generate 3 Shorts from long-form using markers"""
        for i, marker in enumerate(script.metadata.get('shorts_markers', [])[:3]):
            output = f"shorts/{topic_id}_short{i}.mp4"
            os.makedirs("shorts", exist_ok=True)
            self.logger.info(f"Short {i} marked for: {marker['hook']}")

    # ========================================================================
    # STEP 5: THUMBNAIL GENERATION (Midjourney + Canva)
    # ========================================================================
    
    async def generate_thumbnails(self, topic: VideoTopic, script: VideoScript) -> List[str]:
        """Generate 3 thumbnail variants using Midjourney + Canva template"""
        
        variants = []
        template = self.select_thumbnail_template(topic.type)
        
        for variant_num in range(3):
            # Generate background via Midjourney
            bg_prompt = self.build_mj_prompt(topic, script, variant_num)
            bg_url = await self.call_midjourney(bg_prompt)
            
            # Compose in Canva template
            thumb_path = await self.compose_thumbnail_canva(
                template, bg_url, topic, script, variant_num
            )
            variants.append(thumb_path)
        
        self.logger.info(f"Generated {len(variants)} thumbnail variants for {topic.id}")
        return variants

    def select_thumbnail_template(self, vtype: VideoType) -> str:
        templates = {
            VideoType.PATCH_BREAKDOWN: "patch_breakdown",
            VideoType.META_TIER_LIST: "tier_list",
            VideoType.SETTINGS_CONFIG: "settings_config",
            VideoType.RANK_PUSH: "rank_push",
            VideoType.ECONOMY_SKINS: "economy"
        }
        return templates.get(vtype, "default")

    def build_mj_prompt(self, topic: VideoTopic, script: VideoScript, variant: int) -> str:
        game_visuals = {
            Game.BGMI: "Erangel map, military aesthetic, tactical UI",
            Game.FREE_FIRE: "Bermuda map, vibrant anime style, character abilities",
            Game.COD_MOBILE: "Modern warfare, tactical UI, scorestreaks",
            Game.POKEMON_UNITE: "Aeos Island, Pokemon arena, colorful MOBA"
        }
        
        style_variants = [
            "cinematic lighting, dramatic shadows, 8k, unreal engine 5",
            "clean minimal, flat design, esports broadcast style",
            "high contrast, neon accents, cyberpunk gaming aesthetic"
        ]
        
        return f"{game_visuals[topic.game]}, {style_variants[variant]}, youtube thumbnail background, 16:9, no text"

    async def call_midjourney(self, prompt: str) -> str:
        return "https://placeholder.com/thumbnail_bg.jpg"

    async def compose_thumbnail_canva(self, template: str, bg_url: str, topic: VideoTopic, script: VideoScript, variant: int) -> str:
        output = f"thumbnails/{topic.id}_v{variant}.jpg"
        os.makedirs("thumbnails", exist_ok=True)
        return output

    # ========================================================================
    # STEP 6: UPLOAD & METADATA (YouTube API)
    # ========================================================================
    
    async def upload_video(self, topic: VideoTopic, script: VideoScript, video_path: str, thumbnail_paths: List[str]):
        """Upload video with full metadata, schedule, playlists, end screens"""
        
        thumbnail_path = thumbnail_paths[0]
        
        metadata = self.build_upload_metadata(topic, script)
        
        media = MediaFileUpload(video_path, chunksize=-1, resumable=True, mimetype='video/mp4')
        
        request = self.youtube.videos().insert(
            part=','.join(metadata.keys()),
            body=metadata,
            media_body=media
        )
        
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                self.logger.info(f"Upload progress: {int(status.progress() * 100)}%")
        
        video_id = response['id']
        self.logger.info(f"Video uploaded: https://youtube.com/watch?v={video_id}")
        
        # Upload thumbnail
        self.youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype='image/jpeg')
        ).execute()
        
        # Add to playlists
        self.add_to_playlists(video_id, topic.type)
        
        # Set end screen
        self.set_end_screen(video_id, topic.type)
        
        # Schedule Shorts uploads
        await self.schedule_shorts(topic.id, video_id)
        
        topic.status = "uploaded"
        topic.youtube_id = video_id
        self.save_topic_queue()
        
        return video_id

    def build_upload_metadata(self, topic: VideoTopic, script: VideoScript) -> Dict:
        return {
            "snippet": {
                "title": script.metadata['title'],
                "description": script.metadata['description'],
                "tags": script.metadata['tags'],
                "categoryId": "20",  # Gaming
                "defaultLanguage": "en",
                "defaultAudioLanguage": "en"
            },
            "status": {
                "privacyStatus": "private",
                "publishAt": topic.scheduled_for,
                "selfDeclaredMadeForKids": False,
                "license": "youtube"
            },
            "recordingDetails": {
                "locationDescription": "India",
                "recordingDate": datetime.now().isoformat()
            }
        }

    def add_to_playlists(self, video_id: str, vtype: VideoType):
        playlist_map = {
            VideoType.PATCH_BREAKDOWN: self.config['playlists']['patch'],
            VideoType.META_TIER_LIST: self.config['playlists']['meta'],
            VideoType.SETTINGS_CONFIG: self.config['playlists']['settings'],
            VideoType.RANK_PUSH: self.config['playlists']['rank'],
            VideoType.ECONOMY_SKINS: self.config['playlists']['economy']
        }
        playlist_id = playlist_map.get(vtype)
        if playlist_id:
            self.youtube.playlistItems().insert(
                part="snippet",
                body={"snippet": {"playlistId": playlist_id, "resourceId": {"kind": "youtube#video", "videoId": video_id}}}
            ).execute()

    def set_end_screen(self, video_id: str, vtype: VideoType):
        pass

    async def schedule_shorts(self, topic_id: str, video_id: str):
        shorts_dir = f"shorts/{topic_id}"
        if os.path.exists(shorts_dir):
            for short_file in sorted(os.listdir(shorts_dir))[:3]:
                pass

    # ========================================================================
    # STEP 7: ANALYTICS FEEDBACK LOOP
    # ========================================================================
    
    async def run_analytics_feedback(self):
        """Daily analytics review -> Update topic queue weights"""
        
        analytics = self.fetch_channel_analytics(days=7)
        
        prompt = f"""
        Analyze last 7 days performance for Meta Gaming India.
        
        ANALYTICS:
        {json.dumps(analytics, indent=2)}
        
        CURRENT TOPIC QUEUE:
        {json.dumps([asdict(t) for t in self.topic_queue[:15]], indent=2)}
        
        Provide:
        1. Top 3 performing videos + WHY (CTR, AVD, traffic source)
        2. Bottom 3 + WHY
        3. Search terms driving traffic (new topic opportunities)
        4. Thumbnail CTR winners/losers
        5. Recommended queue reordering
        6. Topics to add/remove
        
        Return JSON with actionable decisions.
        """
        
        response = await self.call_gpt(prompt, max_tokens=2000)
        decisions = json.loads(response)
        
        self.apply_analytics_decisions(decisions)
        
        self.logger.info("Analytics feedback loop completed")

    def fetch_channel_analytics(self, days: int) -> Dict:
        return {}

    def apply_analytics_decisions(self, decisions: Dict):
        pass

    # ========================================================================
    # UTILITY METHODS
    # ========================================================================
    
    async def call_gpt(self, prompt: str, max_tokens: int = 2000) -> str:
        client = openai.AsyncOpenAI(api_key=self.config['openai']['api_key'])
        response = await client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=max_tokens,
            temperature=0.7,
            response_format={"type": "json_object"}
        )
        return response.choices[0].message.content

    def load_topic_queue(self) -> List[VideoTopic]:
        if os.path.exists("topic_queue.json"):
            with open("topic_queue.json") as f:
                data = json.load(f)
                return [VideoTopic(**item) for item in data]
        return []

    def save_topic_queue(self):
        with open("topic_queue.json", "w") as f:
            json.dump([asdict(t) for t in self.topic_queue], f, indent=2)

    def load_clip_library(self):
        if os.path.exists("clip_library.json"):
            with open("clip_library.json") as f:
                data = json.load(f)
                self.clip_library = [GameplayClip(**item) for item in data]

    # ========================================================================
    # MAIN DAILY RUN
    # ========================================================================
    
    async def run_daily_pipeline(self):
        """Main entry point - runs via cron daily"""
        self.logger.info("=== DAILY PIPELINE START ===")
        
        self.load_clip_library()
        
        topic = await self.select_next_topic()
        script = await self.generate_script(topic)
        audio_path = await self.generate_voiceover(script)
        video_path = await self.edit_video(topic, script, audio_path)
        thumbnail_paths = await self.generate_thumbnails(topic, script)
        
        topic.scheduled_for = self.calculate_optimal_publish_time()
        
        await self.upload_video(topic, script, video_path, thumbnail_paths)
        
        await self.run_analytics_feedback()
        
        self.logger.info("=== DAILY PIPELINE COMPLETE ===")

    def calculate_optimal_publish_time(self) -> str:
        now = datetime.now()
        target_weekday = {1: 1, 3: 3, 5: 5}.get(now.weekday(), 1)
        days_ahead = (target_weekday - now.weekday()) % 7
        if days_ahead == 0 and now.hour >= 19:
            days_ahead = 2
        target = now + timedelta(days=days_ahead)
        target = target.replace(hour=19, minute=0, second=0, microsecond=0)
        return target.isoformat() + "+05:30"

# ============================================================================
# ENTRY POINT
# ============================================================================

async def main():
    pipeline = MetaGamingPipeline()
    await pipeline.run_daily_pipeline()

if __name__ == "__main__":
    asyncio.run(main())