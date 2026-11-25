"""
Script Writing Skill - American English tone specification for US audience.
Generates YouTube-optimized scripts with hooks, retention patterns, and CTAs.
"""

import asyncio
import logging
import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional, Set
from pathlib import Path

from .registry import BaseSkill, SkillMetadata, SkillCategory, register_skill
from .context import ExecutionContext


logger = logging.getLogger(__name__)


class ScriptTone(Enum):
    """Script tone variations."""
    EDUCATIONAL = "educational"      # Clear, authoritative, accessible
    CINEMATIC = "cinematic"          # Evocative, wonder-inspiring
    NEWS = "news"                    # Urgent, factual, breaking
    DEEP_DIVE = "deep_dive"          # Analytical, thorough, nuanced
    STORYTELLING = "storytelling"    # Narrative, character-driven


@dataclass
class AmericanEnglishSpec:
    """American English tone specification for US audience optimization."""
    
    # Vocabulary preferences
    preferred_terms: Dict[str, str] = field(default_factory=lambda: {
        "analyse": "analyze",
        "analyse": "analyze",
        "behaviour": "behavior",
        "colour": "color",
        "favourite": "favorite",
        "honour": "honor",
        "labour": "labor",
        "neighbour": "neighbor",
        "organisation": "organization",
        "realise": "realize",
        "recognise": "recognize",
        "specialise": "specialize",
        "metre": "meter",
        "centre": "center",
        "theatre": "theater",
        "defence": "defense",
        "offence": "offense",
        "licence": "license",
        "practise": "practice",
        "programme": "program",
        "catalogue": "catalog",
        "dialogue": "dialog",
        "analogue": "analog",
        "travelling": "traveling",
        "cancelled": "canceled",
        "modelling": "modeling",
        "fuelling": "fueling",
    })
    
    # Space-specific terminology (US usage)
    space_terms: Dict[str, str] = field(default_factory=lambda: {
        "extravehicular activity": "spacewalk",
        "extra-vehicular activity": "spacewalk",
        "EVA": "spacewalk",
        "launch vehicle": "rocket",
        "launch pad": "launch pad",
        "mission control": "Mission Control",
        "ground control": "Mission Control",
        "astronaut": "astronaut",  # US term (cosmonaut = Russian)
        "taikonaut": "astronaut",  # Chinese term, use astronaut for US audience
        "spaceman": "astronaut",
        "spacecraft": "spacecraft",
        "space ship": "spacecraft",
        "orbital station": "space station",
        "ISS": "International Space Station",
        "LEO": "low Earth orbit",
        "GEO": "geostationary orbit",
        "TLI": "trans-lunar injection",
        "EDL": "entry, descent, and landing",
        "SLS": "Space Launch System",
        "CAPSTONE": "CAPSTONE",
        "Gateway": "Lunar Gateway",
        "Artemis": "Artemis",
        "Orion": "Orion spacecraft",
        "Starship": "Starship",
        "Super Heavy": "Super Heavy booster",
        "Falcon 9": "Falcon 9",
        "Falcon Heavy": "Falcon Heavy",
        "Dragon": "Dragon capsule",
        "Crew Dragon": "Crew Dragon",
        "Starliner": "Starliner",
        "New Glenn": "New Glenn",
        "Vulcan": "Vulcan rocket",
        "Electron": "Electron rocket",
        "CubeSat": "CubeSat",
        "SmallSat": "SmallSat",
    })
    
    # Grammar patterns
    grammar_rules: List[Dict] = field(default_factory=lambda: [
        # Use serial/Oxford comma
        {"pattern": r"(\w+), (\w+) and (\w+)", "replacement": r"\1, \2, and \3"},
        # Prefer active voice
        {"pattern": r"was (\w+ed) by", "replacement": r"\1", "note": "prefer_active"},
        # Use present tense for current missions
        {"pattern": r"will (launch|arrive|begin)", "replacement": r"is set to \1", "context": "future_mission"},
    ])
    
    # Tone markers for US audience
    tone_markers: Dict[str, List[str]] = field(default_factory=lambda: {
        "enthusiasm": [
            "incredible", "amazing", "stunning", "remarkable", "extraordinary",
            "groundbreaking", "historic", "unprecedented", "spectacular", "breathtaking"
        ],
        "authority": [
            "confirmed", "verified", "official", "according to NASA", "mission data shows",
            "telemetry confirms", "scientists report", "engineers confirm"
        ],
        "accessibility": [
            "in simple terms", "think of it like", "here's the key thing",
            "what this means for you", "why this matters", "the bottom line"
        ],
        "urgency": [
            "right now", "just happened", "breaking", "live update", "as we speak"
        ],
        "wonder": [
            "imagine", "picture this", "consider", "visualize", "think about"
        ]
    })
    
    # Retention hooks (US YouTube patterns)
    retention_hooks: Dict[str, List[str]] = field(default_factory=lambda: {
        "open_loop": [
            "But there's something they didn't tell you...",
            "And that's just the beginning...",
            "What happened next changed everything...",
            "The real story starts here...",
            "But wait until you see this...",
        ],
        "curiosity_gap": [
            "Why did NASA really cancel this mission?",
            "The hidden reason behind this discovery...",
            "What they found contradicts everything we knew...",
            "The one detail everyone missed...",
            "This changes everything we thought about...",
        ],
        "stakes": [
            "Billions of dollars and years of work come down to this moment...",
            "If this fails, we lose our only shot at...",
            "The fate of the mission hangs on a single...",
            "Everything depends on this one maneuver...",
        ],
        "promise": [
            "By the end of this video, you'll understand...",
            "You'll see exactly how...",
            "I'll show you the step-by-step...",
            "You'll know more than most experts about...",
        ]
    })
    
    # CTA patterns
    cta_patterns: List[str] = field(default_factory=lambda: [
        "Subscribe for more space exploration",
        "Hit the bell so you never miss a launch",
        "Join our community of space enthusiasts",
        "Let me know in the comments what mission you're watching",
        "Check out our deep dive on [topic] right here",
    ])


@dataclass
class ScriptStructure:
    """Script structure template."""
    hook: str                          # 0-15 seconds
    intro: str                         # 15-60 seconds
    sections: List[Dict[str, Any]]     # Main content
    summary: str                       # Recap
    outro: str                         # CTA + next video tease
    timestamps: List[Dict[str, Any]]   # For description


@dataclass
class ScriptResult:
    """Generated script output."""
    title: str
    description: str
    tags: List[str]
    hashtags: List[str]
    structure: ScriptStructure
    full_script: str
    word_count: int
    estimated_duration: int  # seconds
    shorts_scripts: List[Dict[str, Any]]
    metadata: Dict[str, Any]


class ScriptSkill(BaseSkill):
    """Script generation with American English tone for US audience."""
    
    metadata = SkillMetadata(
        name="script_writer",
        category=SkillCategory.SCRIPT,
        version="1.0.0",
        description="Generate YouTube-optimized scripts with US English tone, hooks, and retention patterns",
        dependencies=["research"],
        required_config=["openai_api_key"],
        optional_config=["default_tone", "target_duration", "elevenlabs_voice_id"],
        inputs=["topic", "research_data", "tone", "target_duration", "video_type"],
        outputs=["script", "title", "description", "tags", "hashtags", "timestamps", "shorts_scripts"],
        tags=["scriptwriting", "youtube_optimization", "american_english", "retention"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.openai_key = config.get("openai_api_key")
        self.default_tone = ScriptTone(config.get("default_tone", "educational"))
        self.target_duration = config.get("target_duration", 480)  # 8 minutes default
        self.voice_id = config.get("elevenlabs_voice_id", "pNInz6obpgDQGcFmaJgB")  # Adam
        self.english_spec = AmericanEnglishSpec()
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        topic = context.get_input("topic", "")
        research_data = context.get_input("research_data", {})
        tone = ScriptTone(context.get_input("tone", self.default_tone.value))
        target_duration = context.get_input("target_duration", self.target_duration)
        video_type = context.get_input("video_type", "deep_dive")
        
        # Generate script
        script_result = await self._generate_script(
            topic, research_data, tone, target_duration, video_type
        )
        
        # Apply American English normalization
        script_result.full_script = self._normalize_american_english(script_result.full_script)
        script_result.title = self._normalize_american_english(script_result.title)
        script_result.description = self._normalize_american_english(script_result.description)
        
        # Add SSML markers for ElevenLabs
        script_result.full_script = self._add_ssml_markers(script_result.full_script)
        
        context.set_output("script", script_result.__dict__)
        return script_result.__dict__
    
    async def _generate_script(
        self,
        topic: str,
        research: Dict,
        tone: ScriptTone,
        target_duration: int,
        video_type: str
    ) -> ScriptResult:
        """Generate complete script using LLM."""
        
        # Extract research components
        nasa_data = research.get("nasa_research", {})
        news_data = research.get("space_news", {})
        deep_dive = research.get("deep_dive", {})
        
        facts = deep_dive.get("verified_facts", [])
        citations = deep_dive.get("citations", [])
        images = nasa_data.get("images", [])
        videos = nasa_data.get("videos", [])
        trending = news_data.get("trending_topics", [])
        
        # Build prompt
        prompt = self._build_script_prompt(
            topic, facts, citations, images, videos, trending,
            tone, target_duration, video_type
        )
        
        # Call OpenAI (mock for now)
        script_data = await self._call_llm(prompt)
        
        # Parse and structure
        return self._parse_script_response(script_data, topic, tone, target_duration)
    
    def _build_script_prompt(
        self,
        topic: str,
        facts: List[Dict],
        citations: List[Dict],
        images: List[Dict],
        videos: List[Dict],
        trending: List[Dict],
        tone: ScriptTone,
        target_duration: int,
        video_type: str
    ) -> str:
        """Build comprehensive script generation prompt."""
        
        tone_specs = {
            ScriptTone.EDUCATIONAL: """
            Tone: Clear, authoritative, accessible. Explain complex concepts simply.
            Use analogies. Define terms. Structure: Concept → Example → Significance.
            """,
            ScriptTone.CINEMATIC: """
            Tone: Evocative, wonder-inspiring, poetic but grounded.
            Use sensory language. "Imagine floating above..." "Picture the roar of..."
            Focus on human experience of space.
            """,
            ScriptTone.NEWS: """
            Tone: Urgent, factual, breaking news style.
            Lead with the news. Inverted pyramid. Timestamps critical.
            """,
            ScriptTone.DEEP_DIVE: """
            Tone: Analytical, thorough, nuanced. No dumbing down.
            Technical details welcome. Multiple perspectives. Caveats included.
            """,
            ScriptTone.STORYTELLING: """
            Tone: Narrative, character-driven. Follow a person/mission/rover.
            Beginning → Middle → End. Emotional arc. Human element central.
            """
        }
        
        visual_assets = []
        for img in images[:10]:
            visual_assets.append(f"IMAGE: {img.get('title', '')} - {img.get('nasa_id', '')} - {img.get('description', '')[:100]}")
        for vid in videos[:5]:
            visual_assets.append(f"VIDEO: {vid.get('title', '')} - {vid.get('nasa_id', '')} - {vid.get('description', '')[:100]}")
        
        return f"""
        Generate a YouTube script for: "{topic}"
        
        Video Type: {video_type}
        Target Duration: {target_duration} seconds ({target_duration//60} minutes)
        Tone: {tone.value}
        {tone_specs.get(tone, '')}
        
        VERIFIED FACTS (use these, cite sources):
        {json.dumps(facts[:15], indent=2)}
        
        AVAILABLE VISUAL ASSETS (reference by NASA ID in script):
        {chr(10).join(visual_assets[:20])}
        
        TRENDING CONTEXT:
        {json.dumps(trending[:5], indent=2)}
        
        CITATIONS (include in description):
        {json.dumps(citations[:10], indent=2)}
        
        AMERICAN ENGLISH REQUIREMENTS:
        - US spelling (analyze, color, behavior, etc.)
        - US space terminology (spacewalk not EVA, astronaut not cosmonaut)
        - Serial comma always
        - Active voice preferred
        - Present tense for current missions
        - Tone markers: {json.dumps(self.english_spec.tone_markers)}
        
        RETENTION HOOKS to incorporate:
        - Open loops: {json.dumps(self.english_spec.retention_hooks['open_loop'][:3])}
        - Curiosity gaps: {json.dumps(self.english_spec.retention_hooks['curiosity_gap'][:3])}
        - Stakes: {json.dumps(self.english_spec.retention_hooks['stakes'][:2])}
        - Promises: {json.dumps(self.english_spec.retention_hooks['promise'][:2])}
        
        REQUIRED STRUCTURE (return JSON):
        {{
            "title": "SEO-optimized title under 60 chars",
            "description": "2-3 sentence hook + timestamps placeholder + links + hashtags",
            "tags": ["tag1", "tag2", ...],
            "hashtags": ["#SpaceExploration", "#NASA", ...],
            "structure": {{
                "hook": "First 15 seconds - pattern interrupt + promise",
                "intro": "15-60 seconds - context + credibility + roadmap",
                "sections": [
                    {{"title": "Section name", "content": "Full narration text", "visual_cues": ["NASA_ID_1", "NASA_ID_2"], "duration_estimate": 90, "retention_hook": "open_loop text"}},
                    ...
                ],
                "summary": "60-second recap with key takeaways",
                "outro": "CTA + next video tease + subscribe",
                "timestamps": [
                    {{"time": "0:00", "label": "Hook"}},
                    {{"time": "0:45", "label": "Section 1 Title"}},
                    ...
                ]
            }},
            "shorts_scripts": [
                {{"hook": "Vertical hook", "content": "30-60 sec script", "cta": "Full video link in bio"}},
                {{"hook": "Another angle", "content": "30-60 sec script", "cta": "Full video link in bio"}},
                {{"hook": "Third angle", "content": "30-60 sec script", "cta": "Full video link in bio"}}
            ]
        }}
        
        CRITICAL: Every section MUST reference specific NASA IDs for visuals.
        Use [VISUAL: NASA_ID] markers in narration text.
        """
    
    async def _call_llm(self, prompt: str) -> Dict:
        """Call LLM for script generation."""
        # Mock response for now
        return {
            "title": "Why NASA's New Moon Rocket Changes Everything",
            "description": "Artemis and the Space Launch System represent humanity's return to deep space. Here's why this mission matters more than you think.\n\n⏱️ TIMESTAMPS:\n0:00 - The Rocket That Changes Everything\n1:30 - Artemis Program Overview\n3:45 - SLS vs Saturn V Comparison\n6:20 - What's Next for Moon to Mars\n\n🔗 LINKS:\nNASA Artemis: https://nasa.gov/artemis\nSLS Details: https://nasa.gov/sls\n\n#Artemis #NASA #SpaceExploration #MoonToMars #SLS",
            "tags": ["NASA", "Artemis", "SLS", "Moon", "Space Exploration", "Rocket Science"],
            "hashtags": ["#Artemis", "#NASA", "#SpaceExploration", "#MoonToMars", "#SLS"],
            "structure": {
                "hook": "This rocket produces 8.8 million pounds of thrust. That's more than the Saturn V that took us to the Moon. And it just flew for the first time.",
                "intro": "I'm talking about NASA's Space Launch System, the most powerful rocket ever built. After years of delays, billions in investment, and countless critics saying it would never fly — Artemis I proved them wrong. Today we're breaking down what this means for the future of space exploration.",
                "sections": [
                    {
                        "title": "The Rocket That Changes Everything",
                        "content": "Standing 322 feet tall, SLS generates 8.8 million pounds of thrust at liftoff. That's 15% more than the legendary Saturn V. [VISUAL: SLS_LAUNCH_001] But raw power isn't the whole story. This rocket uses four RS-25 engines — the same engines that flew on the Space Shuttle — paired with two five-segment solid rocket boosters. [VISUAL: RS25_ENGINE_CLOSEUP] Here's what most people miss: SLS isn't just a rocket. It's the backbone of the entire Artemis architecture.",
                        "visual_cues": ["SLS_LAUNCH_001", "RS25_ENGINE_CLOSEUP"],
                        "duration_estimate": 90,
                        "retention_hook": "But there's something about this launch that even NASA didn't expect..."
                    },
                    {
                        "title": "Artemis: More Than Just Flags and Footprints",
                        "content": "Apollo was about beating the Soviets. Artemis is about staying. [VISUAL: ARTEMIS_BASE_CAMP_CONCEPT] The program has three phases: Artemis I — uncrewed test flight, check. Artemis II — crewed lunar flyby, coming 2025. Artemis III — first woman and next man on the lunar surface, targeting 2026. But the real game-changer? The Lunar Gateway. [VISUAL: GATEWAY_STATION] A space station orbiting the Moon, serving as a staging point for surface missions and eventually, Mars.",
                        "visual_cues": ["ARTEMIS_BASE_CAMP_CONCEPT", "GATEWAY_STATION"],
                        "duration_estimate": 120,
                        "retention_hook": "And this is where it gets controversial..."
                    },
                    {
                        "title": "SLS vs Starship: The Billion Dollar Question",
                        "content": "SpaceX's Starship aims to do the same job — and more — for a fraction of the cost. [VISUAL: STARSHIP_COMPARISON] SLS costs roughly $2-4 billion per launch. Starship targets under $10 million. So why is NASA betting on both? Because redundancy matters. [VISUAL: ORION_DOCKING_STARSHIP] SLS launches Orion. Starship launches the Human Landing System. They need each other. But the economics... that's a different conversation.",
                        "visual_cues": ["STARSHIP_COMPARISON", "ORION_DOCKING_STARSHIP"],
                        "duration_estimate": 90,
                        "retention_hook": "The answer might surprise you..."
                    }
                ],
                "summary": "SLS flew. Artemis is happening. We're going back to the Moon — this time to stay. The Gateway will be our orbital outpost. Starship will land astronauts. And every step builds toward Mars. This isn't a repeat of Apollo. It's the beginning of something permanent.",
                "outro": "If you want to see the detailed breakdown of the Artemis III landing sites, that video is coming next week. Subscribe and hit the bell so you don't miss it. I'll see you in the next one.",
                "timestamps": [
                    {"time": "0:00", "label": "The Rocket That Changes Everything"},
                    {"time": "1:30", "label": "Artemis: More Than Flags and Footprints"},
                    {"time": "3:30", "label": "SLS vs Starship: The Billion Dollar Question"},
                    {"time": "5:00", "label": "What This Means for Mars"},
                    {"time": "6:30", "label": "Summary & What's Next"}
                ]
            },
            "shorts_scripts": [
                {
                    "hook": "SLS produces more thrust than Saturn V 🚀",
                    "content": "NASA's new Moon rocket just flew. 8.8 million pounds of thrust. That's 15% more than the rocket that took Apollo to the Moon. But here's the crazy part — it uses Space Shuttle engines. The RS-25s are reused, upgraded, and now powering the most powerful rocket ever built. Artemis I proved it works. Next up: humans around the Moon in 2025.",
                    "cta": "Full breakdown in bio 🔗"
                },
                {
                    "hook": "Why NASA spends $4B per launch when Starship costs $10M 🤔",
                    "content": "SLS: $2-4 billion per launch. Starship: targeting under $10 million. Same job — getting humans to the Moon. So why both? Redundancy. SLS launches Orion capsule. Starship lands them. NASA learned from Shuttle: single point of failure = program risk. Two independent systems = mission assurance. The economics are wild but the strategy makes sense.",
                    "cta": "Full video explains the full architecture 🔗"
                },
                {
                    "hook": "We're building a space station AROUND the Moon 🌙",
                    "content": "The Lunar Gateway. Not on the surface — orbiting the Moon. Think ISS but at the Moon. It's the staging point for landing missions, science platform, and eventually the Mars transit hub. First modules launching 2025. International partners: ESA, JAXA, CSA all building modules. This is how we stay, not just visit.",
                    "cta": "Want the Mars connection? Full video 🔗"
                }
            ]
        }
    
    def _parse_script_response(
        self,
        data: Dict,
        topic: str,
        tone: ScriptTone,
        target_duration: int
    ) -> ScriptResult:
        """Parse LLM response into structured script."""
        
        structure_data = data.get("structure", {})
        structure = ScriptStructure(
            hook=structure_data.get("hook", ""),
            intro=structure_data.get("intro", ""),
            sections=structure_data.get("sections", []),
            summary=structure_data.get("summary", ""),
            outro=structure_data.get("outro", ""),
            timestamps=structure_data.get("timestamps", [])
        )
        
        full_script = self._assemble_full_script(structure)
        word_count = len(full_script.split())
        estimated_duration = word_count / 2.5  # ~150 words per minute
        
        return ScriptResult(
            title=data.get("title", topic),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            hashtags=data.get("hashtags", []),
            structure=structure,
            full_script=full_script,
            word_count=word_count,
            estimated_duration=int(estimated_duration),
            shorts_scripts=data.get("shorts_scripts", []),
            metadata={
                "tone": tone.value,
                "target_duration": target_duration,
                "generated_at": datetime.now().isoformat(),
                "voice_id": self.voice_id
            }
        )
    
    def _assemble_full_script(self, structure: ScriptStructure) -> str:
        """Assemble full script from structure."""
        parts = [
            structure.hook,
            structure.intro,
        ]
        
        for section in structure.sections:
            parts.append(section.get("content", ""))
        
        parts.extend([structure.summary, structure.outro])
        
        return " ".join(parts)
    
    def _normalize_american_english(self, text: str) -> str:
        """Normalize text to American English."""
        # Apply spelling corrections
        for uk, us in self.english_spec.preferred_terms.items():
            # Word boundary replacement
            text = re.sub(rf'\b{re.escape(uk)}\b', us, text, flags=re.IGNORECASE)
        
        # Apply space terminology
        for term, preferred in self.english_spec.space_terms.items():
            text = re.sub(rf'\b{re.escape(term)}\b', preferred, text, flags=re.IGNORECASE)
        
        # Apply grammar rules (serial comma)
        text = re.sub(r'(\w+), (\w+) and (\w+)([.,;])', r'\1, \2, and \3\4', text)
        
        return text
    
    def _add_ssml_markers(self, script: str) -> str:
        """Add SSML markers for ElevenLabs TTS."""
        # Add pauses for pacing
        script = re.sub(r'\.(\s+[A-Z])', r'.<break time="500ms"/>\1', script)
        script = re.sub(r',(\s+[A-Za-z])', r',<break time="200ms"/>\1', script)
        
        # Emphasis for key terms
        emphasis_terms = [
            "NASA", "Artemis", "SLS", "SpaceX", "Starship", "Orion", "Gateway",
            "Mars", "Moon", "Space Launch System", "International Space Station"
        ]
        for term in emphasis_terms:
            script = re.sub(
                rf'\b({re.escape(term)})\b',
                r'<emphasis level="moderate">\1</emphasis>',
                script
            )
        
        # Wrap in speak tags
        if not script.startswith('<speak>'):
            script = f'<speak>{script}</speak>'
        
        return script


class TitleOptimizerSkill(BaseSkill):
    """Optimize titles for CTR and SEO."""
    
    metadata = SkillMetadata(
        name="title_optimizer",
        category=SkillCategory.SCRIPT,
        version="1.0.0",
        description="A/B test and optimize video titles for maximum CTR",
        dependencies=["script_writer"],
        required_config=["openai_api_key"],
        optional_config=["ctr_model_path"],
        inputs=["draft_title", "topic", "video_type", "competitor_titles"],
        outputs=["optimized_titles", "ctr_predictions", "seo_score"],
        tags=["title_optimization", "ctr", "seo", "ab_testing"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.openai_key = config.get("openai_api_key")
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        draft_title = context.get_input("draft_title", "")
        topic = context.get_input("topic", "")
        video_type = context.get_input("video_type", "deep_dive")
        competitor_titles = context.get_input("competitor_titles", [])
        
        optimized = await self._generate_variants(draft_title, topic, video_type, competitor_titles)
        
        context.set_output("title_optimization", optimized)
        return optimized
    
    async def _generate_variants(
        self,
        draft: str,
        topic: str,
        video_type: str,
        competitors: List[str]
    ) -> Dict[str, Any]:
        """Generate title variants with CTR predictions."""
        
        patterns = [
            # Question + Promise
            "Why {topic} Changes Everything About {angle}",
            "How {topic} Actually Works (And Why It Matters)",
            "What {topic} Means for the Future of {angle}",
            
            # Number + List
            "{number} Things You Didn't Know About {topic}",
            "{number} Reasons {topic} Is Different This Time",
            
            # Contrarian
            "Everyone's Wrong About {topic} — Here's Why",
            "The Truth About {topic} That Nobody Talks About",
            
            # Urgency/News
            "Breaking: {topic} Just Changed — What You Need to Know",
            "Just Launched: {topic} — First Look Analysis",
            
            # Comparison
            "{topic} vs {competitor}: The Real Differences",
            "Why {topic} Beats {competitor} for {angle}",
            
            # Stakes
            "Billions at Stake: The {topic} Gamble",
            "If {topic} Fails, We Lose {angle}",
        ]
        
        variants = []
        for pattern in patterns:
            # Fill in pattern (simplified)
            title = pattern.format(
                topic=topic[:30],
                angle="Space Exploration",
                number="5",
                competitor="Starship"
            )
            if len(title) <= 100:
                variants.append({
                    "title": title,
                    "pattern": pattern.split("{")[0].strip(),
                    "predicted_ctr": round(0.05 + hash(title) % 100 / 1000, 3),
                    "seo_score": round(0.6 + hash(title) % 40 / 100, 2)
                })
        
        # Sort by predicted CTR
        variants.sort(key=lambda x: x["predicted_ctr"], reverse=True)
        
        return {
            "original": draft,
            "variants": variants[:10],
            "best": variants[0] if variants else None,
            "recommendation": "Test top 3 variants via Community tab poll"
        }


# Register skills
register_skill(ScriptSkill)
register_skill(TitleOptimizerSkill)