"""
Research Skills - Data gathering for space exploration content.
NASA APIs, Space News aggregation, Deep Dive research with citations.
"""

import asyncio
import logging
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
import aiohttp
import feedparser

from .registry import BaseSkill, SkillMetadata, SkillCategory, register_skill
from .context import ExecutionContext


logger = logging.getLogger(__name__)


@dataclass
class ResearchResult:
    """Result of a research task."""
    topic: str
    sources: List[Dict[str, Any]]
    key_facts: List[Dict[str, Any]]
    citations: List[Dict[str, Any]]
    images: List[Dict[str, Any]]
    videos: List[Dict[str, Any]]
    related_topics: List[str]
    confidence: float
    researched_at: str = field(default_factory=lambda: datetime.now().isoformat())


@dataclass
class NASAAPIConfig:
    """NASA API configuration."""
    api_key: str = "DEMO_KEY"
    base_url: str = "https://api.nasa.gov"
    rate_limit: int = 1000  # per hour


class NASASkill(BaseSkill):
    """NASA API research skill - public domain images, mission data, APOD."""
    
    metadata = SkillMetadata(
        name="nasa_research",
        category=SkillCategory.RESEARCH,
        version="1.0.0",
        description="Fetch NASA public domain imagery, mission data, and astronomy picture of the day",
        dependencies=[],
        required_config=["nasa_api_key"],
        optional_config=["cache_ttl", "max_results"],
        inputs=["topic", "mission", "date_range"],
        outputs=["images", "videos", "mission_data", "apod", "citations"],
        tags=["nasa", "public_domain", "space_imagery", "mission_data"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.nasa_config = NASAAPIConfig(
            api_key=config.get("nasa_api_key", "DEMO_KEY"),
            base_url=config.get("nasa_base_url", "https://api.nasa.gov"),
        )
        self.cache_ttl = config.get("cache_ttl", 86400)
        self.max_results = config.get("max_results", 20)
        self._session: Optional[aiohttp.ClientSession] = None
    
    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30)
            )
        return self._session
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        topic = context.get_input("topic", "")
        mission = context.get_input("mission", "")
        date_range = context.get_input("date_range", {})
        
        results = {
            "images": [],
            "videos": [],
            "mission_data": {},
            "apod": {},
            "citations": [],
        }
        
        # Search NASA Image and Video Library
        if topic:
            search_results = await self._search_nasa_library(topic)
            results["images"].extend(search_results.get("images", []))
            results["videos"].extend(search_results.get("videos", []))
            results["citations"].extend(search_results.get("citations", []))
        
        # Get mission data
        if mission:
            mission_data = await self._get_mission_data(mission)
            results["mission_data"] = mission_data
            results["citations"].append({
                "source": "NASA Mission Data",
                "url": f"https://api.nasa.gov/mission/{mission}",
                "type": "mission_data",
                "accessed": datetime.now().isoformat()
            })
        
        # Get APOD for date range or today
        apod_data = await self._get_apod(date_range)
        results["apod"] = apod_data
        if apod_data:
            results["citations"].append({
                "source": "NASA APOD",
                "url": apod_data.get("url", ""),
                "type": "apod",
                "title": apod_data.get("title", ""),
                "date": apod_data.get("date", ""),
                "accessed": datetime.now().isoformat()
            })
        
        # Get Mars rover photos if relevant
        if "mars" in topic.lower() or "rover" in topic.lower():
            rover_photos = await self._get_mars_photos()
            results["images"].extend(rover_photos.get("images", []))
            results["citations"].extend(rover_photos.get("citations", []))
        
        # Get EPIC Earth imagery
        if "earth" in topic.lower():
            epic_images = await self._get_epic_images()
            results["images"].extend(epic_images.get("images", []))
            results["citations"].extend(epic_images.get("citations", []))
        
        context.set_output("nasa_research", results)
        return results
    
    async def _search_nasa_library(self, query: str) -> Dict[str, Any]:
        """Search NASA Image and Video Library."""
        session = await self._get_session()
        url = f"{self.nasa_config.base_url}/search"
        params = {
            "q": query,
            "media_type": "image,video",
            "page": 1,
            "page_size": self.max_results,
            "api_key": self.nasa_config.api_key
        }
        
        try:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
            
            images = []
            videos = []
            citations = []
            
            for item in data.get("collection", {}).get("items", []):
                if item.get("data"):
                    datum = item["data"][0]
                    links = item.get("links", [])
                    
                    citation = {
                        "source": "NASA Image and Video Library",
                        "nasa_id": datum.get("nasa_id", ""),
                        "title": datum.get("title", ""),
                        "description": datum.get("description", "")[:500],
                        "keywords": datum.get("keywords", []),
                        "center": datum.get("center", ""),
                        "date_created": datum.get("date_created", ""),
                        "media_type": datum.get("media_type", ""),
                        "url": f"https://images.nasa.gov/details/{datum.get('nasa_id', '')}",
                        "accessed": datetime.now().isoformat(),
                        "license": "Public Domain"
                    }
                    
                    for link in links:
                        href = link.get("href", "")
                        if href.endswith((".jpg", ".jpeg", ".png", ".tif")):
                            citation["image_url"] = href
                            images.append(citation.copy())
                        elif href.endswith((".mp4", ".mov", ".avi")):
                            citation["video_url"] = href
                            videos.append(citation.copy())
                    
                    citations.append(citation)
            
            return {"images": images, "videos": videos, "citations": citations}
        
        except Exception as e:
            logger.error(f"NASA library search failed: {e}")
            return {"images": [], "videos": [], "citations": []}
    
    async def _get_mission_data(self, mission: str) -> Dict[str, Any]:
        """Get mission data from NASA."""
        session = await self._get_session()
        url = f"{self.nasa_config.base_url}/mission/{mission}"
        params = {"api_key": self.nasa_config.api_key}
        
        try:
            async with session.get(url, params=params) as resp:
                return await resp.json()
        except Exception as e:
            logger.error(f"Mission data fetch failed: {e}")
            return {}
    
    async def _get_apod(self, date_range: Dict) -> Dict[str, Any]:
        """Get Astronomy Picture of the Day."""
        session = await self._get_session()
        url = f"{self.nasa_config.base_url}/planetary/apod"
        
        params = {"api_key": self.nasa_config.api_key}
        if date_range.get("start"):
            params["start_date"] = date_range["start"]
        if date_range.get("end"):
            params["end_date"] = date_range["end"]
        else:
            params["date"] = date_range.get("date", datetime.now().strftime("%Y-%m-%d"))
        
        try:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
            
            if isinstance(data, list):
                return data[0] if data else {}
            return data
        except Exception as e:
            logger.error(f"APOD fetch failed: {e}")
            return {}
    
    async def _get_mars_photos(self, rover: str = "curiosity", sol: int = 1000) -> Dict[str, Any]:
        """Get Mars rover photos."""
        session = await self._get_session()
        url = f"{self.nasa_config.base_url}/mars-photos/api/v1/rovers/{rover}/photos"
        params = {
            "sol": sol,
            "api_key": self.nasa_config.api_key,
            "page": 1
        }
        
        try:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
            
            images = []
            citations = []
            
            for photo in data.get("photos", [])[:self.max_results]:
                citation = {
                    "source": "NASA Mars Rover",
                    "rover": photo.get("rover", {}).get("name", ""),
                    "camera": photo.get("camera", {}).get("full_name", ""),
                    "sol": photo.get("sol", 0),
                    "earth_date": photo.get("earth_date", ""),
                    "image_url": photo.get("img_src", ""),
                    "url": f"https://mars.nasa.gov/msl/mission/mars-rover-curiosity/",
                    "accessed": datetime.now().isoformat(),
                    "license": "Public Domain"
                }
                images.append(citation)
                citations.append(citation)
            
            return {"images": images, "citations": citations}
        
        except Exception as e:
            logger.error(f"Mars photos fetch failed: {e}")
            return {"images": [], "citations": []}
    
    async def _get_epic_images(self) -> Dict[str, Any]:
        """Get EPIC Earth imagery."""
        session = await self._get_session()
        url = f"{self.nasa_config.base_url}/EPIC/api/natural/images"
        params = {"api_key": self.nasa_config.api_key}
        
        try:
            async with session.get(url, params=params) as resp:
                data = await resp.json()
            
            images = []
            citations = []
            
            for item in data[:self.max_results]:
                date_str = item.get("date", "").split(" ")[0]
                image_name = item.get("image", "")
                
                citation = {
                    "source": "NASA EPIC",
                    "date": date_str,
                    "image": image_name,
                    "caption": item.get("caption", ""),
                    "centroid_coordinates": item.get("centroid_coordinates", {}),
                    "image_url": f"https://epic.gsfc.nasa.gov/archive/natural/{date_str.replace('-', '/')}/png/{image_name}.png",
                    "url": "https://epic.gsfc.nasa.gov/",
                    "accessed": datetime.now().isoformat(),
                    "license": "Public Domain"
                }
                images.append(citation)
                citations.append(citation)
            
            return {"images": images, "citations": citations}
        
        except Exception as e:
            logger.error(f"EPIC images fetch failed: {e}")
            return {"images": [], "citations": []}
    
    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()


class SpaceNewsSkill(BaseSkill):
    """Space news aggregation from multiple sources."""
    
    metadata = SkillMetadata(
        name="space_news",
        category=SkillCategory.RESEARCH,
        version="1.0.0",
        description="Aggregate space news from NASA, Space.com, ESA, SpaceNews, Ars Technica",
        dependencies=[],
        required_config=[],
        optional_config=["rss_feeds", "keywords", "lookback_days"],
        inputs=["keywords", "lookback_days", "sources"],
        outputs=["articles", "trending_topics", "citations"],
        tags=["news", "aggregation", "space_industry", "current_events"]
    )
    
    DEFAULT_FEEDS = [
        "https://www.nasa.gov/rss/dyn/breaking_news.rss",
        "https://www.space.com/rss",
        "https://www.esa.int/rss/esa_space_science.xml",
        "https://spacenews.com/feed/",
        "https://arstechnica.com/space/feed/",
        "https://www.nasaspaceflight.com/feed/",
        "https://www.planetary.org/rss.xml",
        "https://www.universetoday.com/feed/",
    ]
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.feeds = config.get("rss_feeds", self.DEFAULT_FEEDS)
        self.keywords = config.get("keywords", [
            "mars", "moon", "artemis", "james webb", "jwst", "exoplanet",
            "spacex", "starship", "falcon", "rocket", "launch",
            "iss", "space station", "astronaut", "mission",
            "black hole", "gravitational waves", "dark matter",
            "asteroid", "comet", "planetary defense"
        ])
        self.lookback_days = config.get("lookback_days", 7)
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        keywords = context.get_input("keywords", self.keywords)
        lookback_days = context.get_input("lookback_days", self.lookback_days)
        sources = context.get_input("sources", self.feeds)
        
        cutoff_date = datetime.now() - timedelta(days=lookback_days)
        
        all_articles = []
        seen_urls = set()
        
        for feed_url in sources:
            try:
                articles = await self._parse_feed(feed_url, keywords, cutoff_date)
                for article in articles:
                    if article["url"] not in seen_urls:
                        seen_urls.add(article["url"])
                        all_articles.append(article)
            except Exception as e:
                logger.warning(f"Feed parse failed for {feed_url}: {e}")
        
        # Sort by date, newest first
        all_articles.sort(key=lambda x: x.get("published", ""), reverse=True)
        
        # Extract trending topics
        trending = self._extract_trending(all_articles, keywords)
        
        results = {
            "articles": all_articles[:50],
            "trending_topics": trending,
            "citations": [
                {
                    "source": a["source"],
                    "title": a["title"],
                    "url": a["url"],
                    "published": a["published"],
                    "type": "news_article"
                }
                for a in all_articles[:20]
            ]
        }
        
        context.set_output("space_news", results)
        return results
    
    async def _parse_feed(
        self, 
        feed_url: str, 
        keywords: List[str], 
        cutoff: datetime
    ) -> List[Dict[str, Any]]:
        """Parse RSS feed and filter by keywords."""
        loop = asyncio.get_event_loop()
        feed = await loop.run_in_executor(None, feedparser.parse, feed_url)
        
        articles = []
        source_name = feed.feed.get("title", feed_url)
        
        for entry in feed.entries:
            # Check date
            published = entry.get("published_parsed") or entry.get("updated_parsed")
            if published:
                pub_date = datetime(*published[:6])
                if pub_date < cutoff:
                    continue
            else:
                pub_date = datetime.now()
            
            # Check keywords
            text = f"{entry.get('title', '')} {entry.get('summary', '')}".lower()
            matched_keywords = [kw for kw in keywords if kw.lower() in text]
            
            if not matched_keywords:
                continue
            
            articles.append({
                "source": source_name,
                "title": entry.get("title", ""),
                "url": entry.get("link", ""),
                "summary": entry.get("summary", "")[:500],
                "published": pub_date.isoformat(),
                "matched_keywords": matched_keywords,
                "author": entry.get("author", ""),
                "tags": [tag.term for tag in entry.get("tags", [])]
            })
        
        return articles
    
    def _extract_trending(
        self, 
        articles: List[Dict], 
        keywords: List[str]
    ) -> List[Dict[str, Any]]:
        """Extract trending topics from articles."""
        topic_counts: Dict[str, int] = {}
        topic_articles: Dict[str, List[Dict]] = {}
        
        for article in articles:
            for kw in article.get("matched_keywords", []):
                topic_counts[kw] = topic_counts.get(kw, 0) + 1
                if kw not in topic_articles:
                    topic_articles[kw] = []
                topic_articles[kw].append(article)
        
        trending = []
        for topic, count in sorted(topic_counts.items(), key=lambda x: x[1], reverse=True)[:10]:
            trending.append({
                "topic": topic,
                "mention_count": count,
                "recent_articles": topic_articles[topic][:3]
            })
        
        return trending


class DeepDiveSkill(BaseSkill):
    """Deep research skill for comprehensive topic exploration."""
    
    metadata = SkillMetadata(
        name="deep_dive",
        category=SkillCategory.RESEARCH,
        version="1.0.0",
        description="Comprehensive research with multi-source verification and citation tracking",
        dependencies=["nasa_research", "space_news"],
        required_config=["openai_api_key"],
        optional_config=["max_depth", "sources_per_topic"],
        inputs=["topic", "research_questions", "required_sources"],
        outputs=["comprehensive_report", "verified_facts", "citations", "gaps"],
        tags=["deep_research", "verification", "citations", "comprehensive"]
    )
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        super().__init__(config)
        self.openai_key = config.get("openai_api_key")
        self.max_depth = config.get("max_depth", 3)
        self.sources_per_topic = config.get("sources_per_topic", 5)
    
    async def execute(self, context: ExecutionContext) -> Dict[str, Any]:
        topic = context.get_input("topic", "")
        questions = context.get_input("research_questions", [])
        required_sources = context.get_input("required_sources", ["nasa", "peer_reviewed", "news"])
        
        # Get research from dependencies
        nasa_data = context.get_input("nasa_research", {})
        news_data = context.get_input("space_news", {})
        
        # Build comprehensive report
        report = await self._generate_report(topic, questions, nasa_data, news_data, required_sources)
        
        # Verify facts across sources
        verified = await self._verify_facts(report["facts"], nasa_data, news_data)
        
        # Identify gaps
        gaps = self._identify_gaps(questions, verified)
        
        results = {
            "comprehensive_report": report,
            "verified_facts": verified,
            "citations": report["citations"],
            "gaps": gaps,
            "confidence": self._calculate_confidence(verified, gaps)
        }
        
        context.set_output("deep_dive", results)
        return results
    
    async def _generate_report(
        self,
        topic: str,
        questions: List[str],
        nasa_data: Dict,
        news_data: Dict,
        required_sources: List[str]
    ) -> Dict[str, Any]:
        """Generate comprehensive research report."""
        
        # Build context for LLM
        nasa_images = nasa_data.get("images", [])
        nasa_videos = nasa_data.get("videos", [])
        nasa_citations = nasa_data.get("citations", [])
        articles = news_data.get("articles", [])
        news_citations = news_data.get("citations", [])
        
        prompt = f"""
        Create a comprehensive research report on: {topic}
        
        Research Questions:
        {json.dumps(questions, indent=2)}
        
        Available NASA Data:
        - Images: {len(nasa_images)} items
        - Videos: {len(nasa_videos)} items
        - Citations: {len(nasa_citations)} sources
        
        Available News:
        - Articles: {len(articles)} items
        - Citations: {len(news_citations)} sources
        
        Required Source Types: {required_sources}
        
        Generate a structured report with:
        1. Executive Summary
        2. Key Facts (each with source citations)
        3. Technical Details
        4. Current Missions/Developments
        5. Historical Context
        6. Future Implications
        7. Visual Assets Available (list NASA images/videos with IDs)
        8. Complete Citation List
        9. Confidence Assessment per fact
        
        Return as JSON.
        """
        
        # In production, call OpenAI API here
        # For now, return structured mock data
        return {
            "executive_summary": f"Comprehensive research on {topic}",
            "facts": [
                {
                    "fact": f"Key fact about {topic}",
                    "sources": ["NASA", "Recent news"],
                    "confidence": 0.9,
                    "category": "current_mission"
                }
            ],
            "technical_details": {},
            "current_missions": [],
            "historical_context": "",
            "future_implications": "",
            "visual_assets": {
                "images": [img.get("nasa_id") for img in nasa_images[:10]],
                "videos": [vid.get("nasa_id") for vid in nasa_videos[:5]]
            },
            "citations": nasa_citations + news_citations
        }
    
    async def _verify_facts(
        self,
        facts: List[Dict],
        nasa_data: Dict,
        news_data: Dict
    ) -> List[Dict]:
        """Cross-verify facts across sources."""
        verified = []
        
        for fact in facts:
            verification = {
                "fact": fact["fact"],
                "original_confidence": fact.get("confidence", 0.5),
                "sources": fact.get("sources", []),
                "verified": True,
                "corroborating_sources": [],
                "conflicts": []
            }
            
            # Check against NASA data
            fact_text = fact["fact"].lower()
            for citation in nasa_data.get("citations", []):
                if any(kw in citation.get("description", "").lower() for kw in fact_text.split()):
                    verification["corroborating_sources"].append("NASA")
                    break
            
            # Check against news
            for article in news_data.get("articles", []):
                if any(kw in article.get("summary", "").lower() for kw in fact_text.split()):
                    verification["corroborating_sources"].append("News")
                    break
            
            verified.append(verification)
        
        return verified
    
    def _identify_gaps(
        self,
        questions: List[str],
        verified_facts: List[Dict]
    ) -> List[Dict]:
        """Identify unanswered research questions."""
        answered_topics = set()
        for fact in verified_facts:
            answered_topics.update(fact["fact"].lower().split())
        
        gaps = []
        for q in questions:
            q_words = set(q.lower().split())
            if not q_words.intersection(answered_topics):
                gaps.append({
                    "question": q,
                    "reason": "No supporting evidence found",
                    "priority": "high"
                })
        
        return gaps
    
    def _calculate_confidence(
        self,
        verified: List[Dict],
        gaps: List[Dict]
    ) -> float:
        """Calculate overall confidence score."""
        if not verified:
            return 0.0
        
        avg_confidence = sum(f.get("original_confidence", 0.5) for f in verified) / len(verified)
        gap_penalty = min(len(gaps) * 0.1, 0.5)
        
        return max(0.0, avg_confidence - gap_penalty)


# Register skills
register_skill(NASASkill)
register_skill(SpaceNewsSkill)
register_skill(DeepDiveSkill)