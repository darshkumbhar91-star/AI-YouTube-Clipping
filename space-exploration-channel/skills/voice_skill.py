"""
Voice Skills - ElevenLabs TTS with SSML, American English pronunciation profiles.
Batch generation, voice cloning, pronunciation dictionary.
"""

import asyncio
import logging
import json
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import aiohttp
import aiofiles

from .registry import BaseSkill, SkillMetadata, SkillCategory, register_skill
from .context import ExecutionContext


logger = logging.getLogger(__name__)


@dataclass
class VoiceProfile:
    """Voice profile for different content types."""
    name: str
    voice_id: str
    stability: float = 0.45
    similarity_boost: float = 0.70
    style: float = 0.20
    use_speaker_boost: bool = True
    model: str = "eleven_multilingual_v2"
    description: str = ""


@dataclass
class PronunciationRule:
    """Custom pronunciation rule."""
    word: str
    phoneme: str  # IPA or CMUdict
    alias: Optional[str] = None  # Alternative spelling


@dataclass
class VoiceSegment:
    """Single voice segment with metadata."""
    segment_id: str
    text: str
    ssml: str
    voice_profile: VoiceProfile
    duration_estimate: float = 0.0
    audio_path: Optional[Path] = None
    checksum: str = ""


# Predefined voice profiles for space content
VOICE_PROFILES = {
    "narrator": VoiceProfile(
        name="narrator",
        voice_id="pNInz6obpgDQGcFmaJgB",  # Adam - deep, authoritative
        stability=0.45,
        similarity_boost=0.70,
        style=0.20,
        description="Main narrator - authoritative, clear, documentary style"
    ),
    "news_anchor": VoiceProfile(
        name="news_anchor",
        voice_id="IKne3meq5aSn9XLyUdCD",  # Josh - professional news
        stability=0.55,
        similarity_boost=0.75,
        style=0.15,
        description="Breaking news style - urgent, clear, professional"
    ),
    "storyteller": VoiceProfile(
        name="storyteller",
        voice_id="VR6AewLTigWG4xSOukaG",  # Arnold - warm, narrative
        stability=0.40,
        similarity_boost=0.65,
        style=0.30,
        description="Storytelling - warm, engaging, wonder-inspiring"
    ),
    "expert": VoiceProfile(
        name="expert",
        voice_id="pNInz6obpgDQGcFmaJgB",  # Adam - same as narrator but different settings
        stability=0.60,
        similarity_boost=0.80,
        style=0.10,
        description="Technical expert - precise, measured, authoritative"
    ),
    "enthusiast": VoiceProfile(
        name="enthusiast",
        voice_id="21m00Tcm4TlvDq8ikWAM",  # Rachel - enthusiastic
        stability=0.35,
        similarity_boost=0.60,
        style=0.40,
        description="Space enthusiast - excited, accessible, passionate"
    ),
}

# Space terminology pronunciation dictionary (CMUdict style)
SPACE_PRONUNCIATIONS = {
    "artemis": "AA R T AH M IH S",
    "orion": "AO R AY AH N",
    "sLS": "EH S EH L EH S",
    "jwst": "JEY D AH B AH L Y UW S P EY S T EH L",
    "james webb": "JHEY M Z W EH B",
    "nasa": "N AE S AH",
    "esa": "IY S AH",
    "iss": "AY EH S EH S",
    "leo": "L IY OW",
    "geo": "J IY OW",
    "tli": "T IY EH L AY",
    "edl": "IY D IY EH L",
    "eva": "IY V IY EY",
    "soyuz": "S OY UH Z",
    "progress": "P R AA G R EH S",
    "kosmos": "K AA S M OW S",
    "vostok": "V AA S T AA K",
    "voshkod": "V AA SH K AA D",
    "apollo": "AH P AA L OW",
    "gemini": "JH EH M AH N AY",
    "mercury": "M ER K Y ER IY",
    "skylab": "S K AY L AE B",
    "shuttle": "SH AH T AH L",
    "columbia": "K AH L AH M B IY AH",
    "challenger": "CH AE L AH N JH ER",
    "discovery": "D IH S K V ER IY",
    "atlantis": "AE T L AE N T IH S",
    "endeavour": "EH N D AH V ER",
    "falcon": "F AE L K AH N",
    "dragon": "D R AE G AH N",
    "starship": "S T AA R SH IH P",
    "super heavy": "S UW P ER H EH V IY",
    "raptor": "R AE P T ER",
    "merlin": "M ER L IH N",
    "kestrel": "K EH S T R AH L",
    "electron": "IH L EH K T AA N",
    "neutron": "N UW T R AA N",
    "new glenn": "N UW G L EH N",
    "vulcan": "V AH L K AH N",
    "ariane": "AE R IY AE N",
    "vega": "V EY G AH",
    "h-IIa": "EY CH T UW EY",
    "h3": "EY CH TH R IY",
    "long march": "L AO NG M AA R CH",
    "cz-5": "S IY Z E T F AY V",
    "pslv": "P IY EH S EH L V IY",
    "gslv": "JH IY EH S EH L V IY",
    "insight": "IH N S AY T",
    "perseverance": "P ER S AH V IY R AH N S",
    "curiosity": "K Y UH R IY AA S AH T IY",
    "opportunity": "AA P ER T UW N AH T IY",
    "spirit": "S P IH R IH T",
    "sojourner": "S OW J ER N ER",
    "pathfinder": "P AE TH F AY N D ER",
    "viking": "V AY K IH NG",
    "voyager": "V OY AH JH ER",
    "pioneer": "P AY AH N IH R",
    "new horizons": "N UW H ER AY Z AH N Z",
    "cassini": "K AH S IY N IY",
    "huygens": "H OY G AH N Z",
    "galileo": "G AE L AH L IY OW",
    "juno": "JH UW N OW",
    "kepler": "K EH P L ER",
    "tess": "T EH S",
    "spitzer": "S P IH T S ER",
    "chandra": "CH AE N D R AH",
    "hubble": "H AH B AH L",
    "webb": "W EH B",
    "roman": "R OW M AH N",
    "euclid": "Y UW K L IH D",
    "gaia": "G AY AH",
    "lisa": "L AY S AH",
    "athena": "AH TH IY N AH",
    "xrism": "EH K S R IH Z AH M",
}


class ElevenLabsSkill(BaseSkill):
    """ElevenLabs TTS with SSML, batch generation, caching."""
    
    metadata = SkillMetadata(
        name="elevenlabs_tts",
        category=SkillCategory.VOICE,
        version="1.0.0",
        description="ElevenLabs TTS with SSML, American English pronunciation, batch generation",
        dependencies=["script_writer"],
        required_config=["api_key"],
        optional_config=["default_voice", "cache_dir", "max_concurrent", "output_format"],
        inputs=["script", "voice_profile", "pronunciation_overrides"],
        outputs=["audio_files", "segments", "timing_data", "checksums"],
        tags=["elevenlabs", "tts", "ssml", "voice", "batch", "american_english"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.base_url = "https://api.elevenlabs.io/v1"
        self.default_voice = config.get("default_voice", "narrator")
        self.cache_dir = Path(config.get("cache_dir", "cache/voice"))
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.max_concurrent = config.get("max_concurrent", 3)
        self.output_format = config.get("output_format", "mp3_44100_128")
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._session: Optional[aiohttp.ClientSession] = None
        
        # Pronunciation dictionary
        self.pronunciations = SPACE_PRONUNCIATIONS.copy()
        if config.get("custom_pronunciations"):
            self.pronunciations.update(config["custom_pronunciations"])
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=120),
                headers={"xi-api-key": self.api_key}
            )
        return self._session
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        script = context.get_input("script", {})
        voice_profile_name = context.get_input("voice_profile", self.default_voice)
        pronunciation_overrides = context.get_input("pronunciation_overrides", {})
        
        # Merge pronunciations
        self.pronunciations.update(pronunciation_overrides)
        
        # Get voice profile
        voice_profile = VOICE_PROFILES.get(voice_profile_name, VOICE_PROFILES["narrator"])
        
        # Extract script text
        full_script = script.get("full_script", "")
        structure = script.get("structure", {})
        sections = structure.get("sections", [])
        
        # Generate segments
        segments = await self._create_segments(full_script, structure, voice_profile)
        
        # Generate audio for each segment
        audio_results = await self._generate_batch(segments)
        
        # Combine if needed
        final_audio = await self._combine_audio(audio_results, script.get("topic_id", "output"))
        
        # Generate timing data
        timing = self._generate_timing(segments, audio_results)
        
        results = {
            "audio_files": [str(r["path"]) for r in audio_results if r.get("path")],
            "final_audio": str(final_audio) if final_audio else None,
            "segments": [self._segment_to_dict(s) for s in segments],
            "timing_data": timing,
            "checksums": [r.get("checksum", "") for r in audio_results],
            "voice_profile": voice_profile.name,
            "total_duration": sum(r.get("duration", 0) for r in audio_results)
        }
        
        context.set_output("voice", results)
        return results
    
    async def _create_segments(
        self, 
        full_script: str, 
        structure: Dict, 
        voice_profile: VoiceProfile
    ) -> List[VoiceSegment]:
        """Create voice segments from script structure."""
        segments = []
        
        # Hook segment
        hook = structure.get("hook", "")
        if hook:
            segments.append(VoiceSegment(
                segment_id="hook",
                text=hook,
                ssml=self._text_to_ssml(hook, voice_profile),
                voice_profile=voice_profile
            ))
        
        # Intro segment
        intro = structure.get("intro", "")
        if intro:
            segments.append(VoiceSegment(
                segment_id="intro",
                text=intro,
                ssml=self._text_to_ssml(intro, voice_profile),
                voice_profile=voice_profile
            ))
        
        # Section segments
        for i, section in enumerate(structure.get("sections", [])):
            content = section.get("content", "")
            if content:
                segments.append(VoiceSegment(
                    segment_id=f"section_{i}",
                    text=content,
                    ssml=self._text_to_ssml(content, voice_profile),
                    voice_profile=voice_profile
                ))
        
        # Summary segment
        summary = structure.get("summary", "")
        if summary:
            segments.append(VoiceSegment(
                segment_id="summary",
                text=summary,
                ssml=self._text_to_ssml(summary, voice_profile),
                voice_profile=voice_profile
            ))
        
        # Outro segment
        outro = structure.get("outro", "")
        if outro:
            segments.append(VoiceSegment(
                segment_id="outro",
                text=outro,
                ssml=self._text_to_ssml(outro, voice_profile),
                voice_profile=voice_profile
            ))
        
        return segments
    
    def _text_to_ssml(self, text: str, profile: VoiceProfile) -> str:
        """Convert text to SSML with pronunciation and prosody."""
        
        # Apply pronunciation dictionary
        for word, phoneme in self.pronunciations.items():
            # Word boundary replacement with phoneme tag
            pattern = rf'\b{re.escape(word)}\b'
            replacement = f'<phoneme alphabet="cmu" ph="{phoneme}">{word}</phoneme>'
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)
        
        # Add prosody for emphasis
        emphasis_words = [
            "NASA", "Artemis", "SLS", "SpaceX", "Starship", "Orion", "Gateway",
            "Mars", "Moon", "historic", "first", "never", "always", "impossible",
            "breakthrough", "milestone", "critical", "essential", "vital"
        ]
        
        for word in emphasis_words:
            pattern = rf'\b({re.escape(word)})\b'
            text = re.sub(pattern, r'<emphasis level="moderate">\1</emphasis>', text, flags=re.IGNORECASE)
        
        # Add pauses for pacing
        # Comma pauses
        text = re.sub(r',(\s+)', r',<break time="250ms"/>\1', text)
        # Period pauses
        text = re.sub(r'\.(\s+[A-Z])', r'.<break time="500ms"/>\1', text)
        # Colon/semicolon
        text = re.sub(r'[;:](\s+)', r'<break time="350ms"/>\1', text)
        # Paragraph breaks
        text = re.sub(r'\n\n', r'<break time="1000ms"/>', text)
        text = re.sub(r'\n', r'<break time="700ms"/>', text)
        
        # Add prosody for numbers and units
        text = re.sub(
            r'(\d+(?:,\d{3})*(?:\.\d+)?)\s*(million|billion|trillion|thousand)',
            r'<say-as interpret-as="cardinal">\1</say-as> \2',
            text
        )
        
        # Dates
        text = re.sub(
            r'\b(\d{1,2})/(\d{1,2})/(\d{4})\b',
            r'<say-as interpret-as="date" format="mdy">\1/\2/\3</say-as>',
            text
        )
        
        # Wrap in speak tag with voice settings
        ssml = f'''
        <speak>
            <prosody rate="0.95" pitch="0%" volume="medium">
                {text}
            </prosody>
        </speak>
        '''
        
        return ssml.strip()
    
    async def _generate_batch(self, segments: List[VoiceSegment]) -> List[Dict]:
        """Generate audio for all segments concurrently."""
        tasks = [self._generate_segment(seg) for seg in segments]
        return await asyncio.gather(*tasks)
    
    async def _generate_segment(self, segment: VoiceSegment) -> Dict:
        """Generate audio for single segment with caching."""
        async with self._semaphore:
            # Check cache
            cache_key = self._get_cache_key(segment)
            cached_path = self.cache_dir / f"{cache_key}.mp3"
            
            if cached_path.exists():
                logger.info(f"Cache hit: {segment.segment_id}")
                checksum = self._file_checksum(cached_path)
                return {
                    "segment_id": segment.segment_id,
                    "path": cached_path,
                    "checksum": checksum,
                    "cached": True,
                    "duration": self._estimate_duration(segment.text)
                }
            
            # Generate via API
            session = await self._get_session()
            profile = segment.voice_profile
            
            url = f"{self.base_url}/text-to-speech/{profile.voice_id}"
            data = {
                "text": segment.ssml,
                "model_id": profile.model,
                "voice_settings": {
                    "stability": profile.stability,
                    "similarity_boost": profile.similarity_boost,
                    "style": profile.style,
                    "use_speaker_boost": profile.use_speaker_boost
                }
            }
            
            try:
                async with session.post(url, json=data) as resp:
                    if resp.status != 200:
                        error = await resp.text()
                        logger.error(f"ElevenLabs API error: {error}")
                        return {"segment_id": segment.segment_id, "error": error}
                    
                    audio_data = await resp.read()
                
                # Save to cache
                async with aiofiles.open(cached_path, 'wb') as f:
                    await f.write(audio_data)
                
                checksum = self._file_checksum(cached_path)
                duration = self._estimate_duration(segment.text)
                
                return {
                    "segment_id": segment.segment_id,
                    "path": cached_path,
                    "checksum": checksum,
                    "cached": False,
                    "duration": duration
                }
            
            except Exception as e:
                logger.error(f"Segment generation failed: {e}")
                return {"segment_id": segment.segment_id, "error": str(e)}
    
    def _get_cache_key(self, segment: VoiceSegment) -> str:
        """Generate cache key from segment content and voice settings."""
        profile = segment.voice_profile
        key_data = f"{segment.text}|{profile.voice_id}|{profile.stability}|{profile.similarity_boost}|{profile.style}"
        return hashlib.sha256(key_data.encode()).hexdigest()[:16]
    
    def _file_checksum(self, path: Path) -> str:
        """Calculate file checksum."""
        import hashlib
        hasher = hashlib.md5()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()
    
    def _estimate_duration(self, text: str) -> float:
        """Estimate audio duration from text (words per minute)."""
        words = len(text.split())
        # Average 150 words per minute = 2.5 words per second
        return words / 2.5
    
    async def _combine_audio(self, results: List[Dict], topic_id: str) -> Optional[Path]:
        """Combine audio segments into final file."""
        valid_paths = [Path(r["path"]) for r in results if r.get("path") and Path(r["path"]).exists()]
        
        if not valid_paths:
            return None
        
        if len(valid_paths) == 1:
            return valid_paths[0]
        
        output_dir = Path("output/voice")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{topic_id}_final.mp3"
        
        # Create concat file
        concat_file = output_dir / f"{topic_id}_concat.txt"
        with open(concat_file, 'w') as f:
            for path in valid_paths:
                f.write(f"file '{path.absolute()}'\n")
        
        # Concatenate with ffmpeg
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", str(concat_file), "-c", "copy", str(output_path)
        ]
        
        proc = await asyncio.create_subprocess_exec(*cmd)
        await proc.communicate()
        
        concat_file.unlink(missing_ok=True)
        
        return output_path if output_path.exists() else None
    
    def _generate_timing(self, segments: List[VoiceSegment], results: List[Dict]) -> Dict:
        """Generate timing data for caption sync."""
        timing = {
            "segments": [],
            "total_duration": 0.0
        }
        
        current_time = 0.0
        
        for segment, result in zip(segments, results):
            duration = result.get("duration", self._estimate_duration(segment.text))
            
            timing["segments"].append({
                "segment_id": segment.segment_id,
                "start": current_time,
                "end": current_time + duration,
                "duration": duration,
                "text": segment.text[:100] + "..." if len(segment.text) > 100 else segment.text
            })
            
            current_time += duration
        
        timing["total_duration"] = current_time
        return timing
    
    def _segment_to_dict(self, segment: VoiceSegment) -> Dict:
        return {
            "segment_id": segment.segment_id,
            "text": segment.text,
            "ssml": segment.ssml,
            "voice_profile": segment.voice_profile.name,
            "duration_estimate": segment.duration_estimate
        }


class VoiceCloneSkill(BaseSkill):
    """Voice cloning for consistent branding (requires ElevenLabs Creator+)."""
    
    metadata = SkillMetadata(
        name="voice_clone",
        category=SkillCategory.VOICE,
        version="1.0.0",
        description="Create and manage custom voice clones for brand consistency",
        dependencies=["elevenlabs_tts"],
        required_config=["api_key", "training_audio_dir"],
        optional_config=["voice_name", "description", "labels"],
        inputs=["training_files", "voice_name", "description"],
        outputs=["voice_id", "voice_metadata", "verification_samples"],
        tags=["voice_clone", "custom_voice", "branding", "elevenlabs"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.api_key = config.get("api_key")
        self.training_dir = Path(config.get("training_audio_dir", "assets/voice_training"))
        self.base_url = "https://api.elevenlabs.io/v1"
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        training_files = context.get_input("training_files", [])
        voice_name = context.get_input("voice_name", "Space Explained Narrator")
        description = context.get_input("description", "Custom voice for space exploration channel")
        
        if not training_files:
            # Auto-discover training files
            training_files = list(self.training_dir.glob("*.mp3")) + list(self.training_dir.glob("*.wav"))
        
        if not training_files:
            return {"error": "No training audio files found"}
        
        voice_id = await self._create_voice(training_files, voice_name, description)
        
        results = {
            "voice_id": voice_id,
            "voice_name": voice_name,
            "description": description,
            "training_files": [str(f) for f in training_files],
            "created_at": datetime.now().isoformat()
        }
        
        context.set_output("voice_clone", results)
        return results
    
    async def _create_voice(
        self, 
        files: List[Path], 
        name: str, 
        description: str
    ) -> str:
        """Create voice clone via ElevenLabs API."""
        session = aiohttp.ClientSession(headers={"xi-api-key": self.api_key})
        
        try:
            # Prepare multipart form data
            data = aiohttp.FormData()
            data.add_field('name', name)
            data.add_field('description', description)
            
            for i, file_path in enumerate(files):
                with open(file_path, 'rb') as f:
                    data.add_field(
                        f'files',
                        f,
                        filename=file_path.name,
                        content_type='audio/mpeg'
                    )
            
            async with session.post(f"{self.base_url}/voices/add", data=data) as resp:
                result = await resp.json()
                return result.get("voice_id", "")
        
        finally:
            await session.close()


class PronunciationSkill(BaseSkill):
    """Manage pronunciation dictionary for space terminology."""
    
    metadata = SkillMetadata(
        name="pronunciation_manager",
        category=SkillCategory.VOICE,
        version="1.0.0",
        description="Manage custom pronunciation dictionary for space terms",
        dependencies=[],
        required_config=["dictionary_path"],
        optional_config=["auto_learn", "cmu_dict_path"],
        inputs=["terms", "action", "phonemes"],
        outputs=["dictionary", "validation_report"],
        tags=["pronunciation", "dictionary", "cmu", "ipa", "space_terms"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.dict_path = Path(config.get("dictionary_path", "config/pronunciation.json"))
        self.dict_path.parent.mkdir(parents=True, exist_ok=True)
        self.pronunciations = self._load_dictionary()
    
    def _load_dictionary(self) -> Dict:
        """Load pronunciation dictionary."""
        if self.dict_path.exists():
            with open(self.dict_path) as f:
                return json.load(f)
        return SPACE_PRONUNCIATIONS.copy()
    
    def _save_dictionary(self):
        """Save pronunciation dictionary."""
        with open(self.dict_path, 'w') as f:
            json.dump(self.pronunciations, f, indent=2)
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        action = context.get_input("action", "get")
        terms = context.get_input("terms", [])
        phonemes = context.get_input("phonemes", {})
        
        if action == "add":
            self.pronunciations.update(phonemes)
            self._save_dictionary()
            return {"status": "added", "count": len(phonemes)}
        
        elif action == "remove":
            for term in terms:
                self.pronunciations.pop(term.lower(), None)
            self._save_dictionary()
            return {"status": "removed", "count": len(terms)}
        
        elif action == "validate":
            report = self._validate_dictionary()
            return {"status": "validated", "report": report}
        
        elif action == "export_cmu":
            cmu_format = self._export_cmu()
            return {"status": "exported", "cmu_dictionary": cmu_format}
        
        # Default: return dictionary
        return {
            "dictionary": self.pronunciations,
            "count": len(self.pronunciations),
            "categories": self._categorize_terms()
        }
    
    def _validate_dictionary(self) -> Dict:
        """Validate pronunciation dictionary entries."""
        issues = []
        valid = 0
        
        for term, phoneme in self.pronunciations.items():
            if not phoneme:
                issues.append(f"Empty phoneme for: {term}")
            elif not re.match(r'^[A-Z0-9\s\.\-]+$', phoneme):
                issues.append(f"Invalid CMU format for {term}: {phoneme}")
            else:
                valid += 1
        
        return {
            "total": len(self.pronunciations),
            "valid": valid,
            "issues": issues
        }
    
    def _export_cmu(self) -> str:
        """Export in CMUdict format."""
        lines = []
        for term, phoneme in sorted(self.pronunciations.items()):
            # CMUdict format: WORD  PHONEME1 PHONEME2 ...
            lines.append(f"{term.upper()}  {phoneme}")
        return "\n".join(lines)
    
    def _categorize_terms(self) -> Dict[str, List[str]]:
        """Categorize terms by type."""
        categories = {
            "missions": [],
            "vehicles": [],
            "bodies": [],
            "agencies": [],
            "concepts": [],
            "people": [],
            "other": []
        }
        
        # Simple keyword-based categorization
        mission_keywords = ["artemis", "apollo", "voyager", "cassini", "juno", "kepler", "tess", "hubble", "webb"]
        vehicle_keywords = ["falcon", "dragon", "starship", "sls", "orion", "gateway", "soyuz", "progress", "ariane", "vega", "electron", "neutron"]
        body_keywords = ["mars", "moon", "earth", "venus", "jupiter", "saturn", "iss", "leo", "geo"]
        agency_keywords = ["nasa", "esa", "jaxa", "roscosmos", "cnsa", "isro", "spacex", "blue origin"]
        
        for term in self.pronunciations:
            term_lower = term.lower()
            if any(kw in term_lower for kw in mission_keywords):
                categories["missions"].append(term)
            elif any(kw in term_lower for kw in vehicle_keywords):
                categories["vehicles"].append(term)
            elif any(kw in term_lower for kw in body_keywords):
                categories["bodies"].append(term)
            elif any(kw in term_lower for kw in agency_keywords):
                categories["agencies"].append(term)
            else:
                categories["other"].append(term)
        
        return categories


# Register skills
register_skill(ElevenLabsSkill)
register_skill(VoiceCloneSkill)
register_skill(PronunciationSkill)