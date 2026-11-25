# Space Exploration Channel - Fully Automated YouTube Pipeline

> **Zero-copyright, US-audience optimized, 90% automated space exploration content factory**

## 🎯 Overview

This is a complete, production-ready automation system for a "Space Exploration" YouTube channel targeting US audiences (highest RPM: $15-30). The system uses only **legal, zero-copyright sources**: NASA public domain, Pexels/Pixabay royalty-free, and Internet Archive public domain footage.

### Key Features

- 🚀 **90% Automation** - Human only reviews; AI handles research, scripting, VFX, voice, editing, upload
- ⚖️ **Zero Copyright Risk** - Only public domain (NASA), CC0, CC-BY, royalty-free sources
- 🇺🇸 **US Audience Optimized** - American English tone, vocabulary, grammar, cultural references
- 💰 **Multiple Revenue Streams** - AdSense, sponsorships, affiliates, courses, merch, Patreon
- 📈 **Phase-Based Scaling** - Channel Setup → Content Pipeline → Optimization → Multi-channel Empire

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
                    SPACE EXPLORATION ORCHESTRATOR
└─────────────────────────────────────────────────────────────────────┘
                                    │
        ┌───────────────┬───────────┴───────────┬───────────────┐
        ▼               ▼                       ▼               ▼
┌───────────────┐ ┌───────────────┐     ┌───────────────┐ ┌───────────────┐
│   RESEARCH    │ │    SCRIPT     │     │     VFX       │ │    VOICE      │
│  (Skills)     │ │  (Skills)     │     │  (Skills)     │ │  (Skills)     │
├───────────────┤ ├───────────────┤     ├───────────────┤ ├───────────────┤
│ • NASA API    │ │ • US English  │     │ • NASA Footage│ │ • ElevenLabs  │
│ • Space News  │ │ • Hook/Retain │     │ • Blender M.G.│ │ • SSML        │
│ • Deep Dive   │ │ • SEO Title   │     │ • DaVinci Comp│ │ • Pronunciation│
└───────────────┘ └───────────────┘     └───────────────┘ └───────────────┘
        │               │                       │               │
        └───────────────┴───────────┬───────────┴───────────────┘
                                    ▼
                         ┌───────────────────────┐
                         │   YOUTUBE AUTOMATION  │
                         │   (Phase 1-4 Skills)  │
                         ├───────────────────────┤
                         │ • Channel Setup       │
                         │ • Content Pipeline    │
                         │ • A/B Optimization    │
                         │ • Scaling & Revenue   │
                         └───────────────────────┘
```

---

## 📦 Skill Modules

### Research Skills
| Skill | Description | Sources |
|-------|-------------|---------|
| `nasa_research` | NASA public domain imagery, mission data, APOD, Mars rovers, EPIC Earth | NASA API (public domain) |
| `space_news` | Aggregated space news from NASA, Space.com, ESA, Ars Technica, etc. | RSS feeds (fair use) |
| `deep_dive` | Multi-source verification, citation tracking, gap analysis | All above + cross-reference |

### Script Skills
| Skill | Description | Features |
|-------|-------------|----------|
| `script_writer` | Full YouTube script with hooks, retention, CTAs | US English tone, SSML, visual cues |
| `title_optimizer` | A/B title variants with CTR prediction | SEO + click optimization |

### VFX Skills
| Skill | Description | Tools |
|-------|-------------|-------|
| `nasa_footage` | Download, transcode, proxy, catalog NASA assets | ffmpeg, NASA API |
| `motion_graphics` | Orbital mechanics, data viz, UI overlays | Blender 4.0+ |
| `compositing` | Final edit: footage + graphics + color grade | DaVinci Resolve |
| `rife_interpolation` | 60fps/120fps smooth slow-motion | RIFE v4.6 (Vulkan/CUDA) |

### Voice Skills
| Skill | Description | Features |
|-------|-------------|----------|
| `elevenlabs_tts` | Batch TTS with SSML, caching, pronunciation | ElevenLabs API |
| `pronunciation_manager` | Space terminology dictionary (CMUdict) | Auto-learn + validation |

### YouTube Automation Skills (4 Phases)
| Phase | Skill | Description |
|-------|-------|-------------|
| **1** | `phase1_channel_setup` | Branding, SEO, playlists, monetization prep |
| **2** | `phase2_content_pipeline` | Topic queue → Research → Script → VFX → Voice → Upload |
| **3** | `phase3_optimization` | Thumbnail A/B, title optimization, retention analysis, SEO |
| **4** | `phase4_scaling` | Shorts automation, localization, sponsorships, team hiring |

---

## 🚀 Quick Start

### Prerequisites
- Python 3.11+
- NVIDIA GPU (for RIFE, Blender, DaVinci) - **or** CPU-only mode
- FFmpeg, Blender 4.0+, DaVinci Resolve Studio
- API Keys: OpenAI, ElevenLabs, YouTube OAuth, NASA (DEMO_KEY works)

### Local Development

```bash
# Clone and setup
git clone <repo>
cd space-exploration-channel

# Initial setup (creates venv, downloads models, creates dirs)
./manage.sh setup

# Edit config with your API keys
nano config/orchestrator.yaml

# Test individual skills
./manage.sh test nasa_research --topic "Artemis III"
./manage.sh test script_writer --topic "Mars Sample Return"
./manage.sh test elevenlabs_tts --text "Hello from space!"

# Add topics to queue
./manage.sh add-topic "Artemis III Landing Sites" planetary_science 9
./manage.sh add-topic "JWST Deep Field Explained" cosmology 8

# Run daily production batch (3 videos)
./manage.sh daily

# Or run continuous automation
./manage.sh continuous
```

### Docker Deployment

```bash
# Configure environment
cp .env.example .env
nano .env  # Add your API keys

# Build and start
docker-compose up -d --build

# With monitoring
docker-compose --profile monitoring up -d

# With web dashboard
docker-compose --profile web up -d

# View logs
docker-compose logs -f orchestrator
```

### VPS Production Deployment

```bash
# On fresh Ubuntu 22.04+ server
curl -fsSL https://raw.githubusercontent.com/yourrepo/space-exploration-channel/main/deploy.sh | bash

# Or manually:
# 1. Run deploy.sh as root
# 2. Edit /opt/space-exploration/config/orchestrator.yaml
# 3. space-manage start
# 4. space-manage logs
```

---

## ⚙️ Configuration

### Main Config: `config/orchestrator.yaml`

```yaml
channel:
  name: "Space Explained"
  handle: "@SpaceExplained"
  upload_schedule:
    days: ["tuesday", "thursday", "saturday"]
    time: "18:00"
    timezone: "US/Eastern"

skills:
  elevenlabs_tts:
    api_key: "YOUR_ELEVENLABS_KEY"      # REQUIRED
  script_writer:
    openai_api_key: "YOUR_OPENAI_KEY"   # REQUIRED
  youtube_auth:
    client_secrets_file: "config/youtube_client_secrets.json"
```

### YouTube OAuth Setup
1. Google Cloud Console → APIs & Services → Credentials
2. Create OAuth 2.0 Client ID (Desktop app)
3. Download JSON → `config/youtube_client_secrets.json`
4. First run opens browser for authorization

### API Keys Needed
| Service | Purpose | Free Tier |
|---------|---------|-----------|
| OpenAI | Scripts, research, titles | $5 credit |
| ElevenLabs | Voiceover (Adam voice) | 10k chars/mo |
| NASA | Imagery, mission data | DEMO_KEY (1000/hr) |
| YouTube | Upload, analytics | Free |
| Pexels/Pixabay | B-roll footage | Free (attribution) |

---

## 📊 Content Strategy

### Content Pillars (Balanced Rotation)
| Pillar | % | Examples | Automation Ease |
|--------|---|----------|-----------------|
| Planetary Science | 20% | Mars geology, Venus atmosphere, Moon water | ⭐⭐⭐⭐⭐ |
| Space Technology | 20% | Rockets, engines, satellites, stations | ⭐⭐⭐⭐ |
| Cosmology | 15% | Black holes, dark matter, universe origin | ⭐⭐⭐⭐ |
| Exoplanets | 15% | JWST discoveries, habitable worlds, biosignatures | ⭐⭐⭐⭐ |
| Missions | 15% | Artemis, Mars Sample Return, Europa Clipper | ⭐⭐⭐⭐⭐ |
| Space News | 15% | Weekly launches, policy, industry updates | ⭐⭐⭐⭐⭐ |

### Video Types & Templates
| Type | Duration | Structure | Retention Hooks |
|------|----------|-----------|-----------------|
| **Deep Dive** | 8-12 min | Hook → Context → 3-4 Sections → Summary → CTA | Open loops, stakes, promises |
| **Mission Breakdown** | 5-8 min | Hook → Timeline → Tech → Significance → Future | Curiosity gaps, visual reveals |
| **News/Update** | 3-5 min | Breaking → Details → Implications → What's Next | Urgency, first-look |
| **Shorts** | 30-60s | Hook → Fact → Visual → CTA | Pattern interrupt, single fact |

### Upload Schedule
- **Long-form**: Tue/Thu/Sat 6:00 PM EST (US prime time)
- **Shorts**: Daily 12:00 PM EST (algorithmic boost)
- **Community**: Mon/Wed/Fri (polls, behind-scenes, Q&A)

---

## 💰 Revenue Projections

### Phase 1 (Months 1-3): Foundation
| Metric | Target |
|--------|--------|
| Videos | 36 (3/week) |
| Subscribers | 5,000 |
| Monthly Views | 200K |
| Revenue | $200-500 (AdSense only) |

### Phase 2 (Months 4-6): Optimization
| Metric | Target |
|--------|--------|
| Videos | 50+ |
| Subscribers | 25,000 |
| Monthly Views | 1M |
| Revenue | $3,000-8,000 (AdSense + Sponsors + Affiliates) |

### Phase 3 (Months 7-12): Scaling
| Metric | Target |
|--------|--------|
| Videos | 60+ |
| Subscribers | 100,000 |
| Monthly Views | 4M |
| Revenue | $15,000-40,000 (All streams) |

### Revenue Mix Target (12 Months)
| Stream | % | Strategy |
|--------|---|----------|
| AdSense | 35% | High RPM niche, US audience |
| Sponsorships | 30% | VPN, courses, telescopes, tech |
| Affiliates | 10% | Amazon (books/gear), courses, VPN |
| Courses | 15% | "Rocket Science 101", "Orbital Mechanics" |
| Merch | 5% | Mission patches, blueprints, posters |
| Patreon | 5% | Discord, ad-free, Q&A, early access |

---

## 🛠️ Management Commands

```bash
# Service management
./manage.sh start|stop|restart|status|logs

# Production
./manage.sh daily              # Run 3-video batch
./manage.sh continuous         # 24/7 automation
./manage.sh phase1             # Channel setup
./manage.sh phase2             # Content pipeline
./manage.sh phase3             # Analytics optimization
./manage.sh phase4             # Scaling plan

# Queue management
./manage.sh status             # Orchestrator status
./manage.sh queue              # Show topic queue
./manage.sh add-topic "Title" pillar priority

# Testing
./manage.sh test nasa_research --topic "Mars"
./manage.sh test script_writer --topic "JWST"
./manage.sh test elevenlabs_tts --text "Test"

# Maintenance
./manage.sh backup             # Backup config/state/assets
./manage.sh restore backup.tar.gz
./manage.sh clean              # Clean temp files
./manage.sh update             # Update dependencies
```

---

## 📁 Directory Structure

```
space-exploration-channel/
├── skills/                    # All skill modules
│   ├── __init__.py           # Core framework exports
│   ├── registry.py           # Skill registry & discovery
│   ├── pipeline.py           # Pipeline orchestration
│   ├── context.py            # Shared context & cache
│   ├── modifier.py           # Cross-cutting modifiers
│   ├── research_skill.py     # NASA, News, Deep Dive
│   ├── script_skill.py       # US English scripts
│   ├── vfx_skill.py          # NASA footage, Blender, DaVinci
│   ├── voice_skill.py        # ElevenLabs, pronunciation
│   ├── youtube_automation_skill.py  # Phase 1-4
│   └── orchestrator.py       # Master coordinator
├── config/
│   └── orchestrator.yaml     # Main configuration
├── assets/
│   ├── nasa/                 # Downloaded NASA footage
│   ├── branding/             # Logo, banner, watermark
│   └── luts/                 # Color grading LUTs
├── templates/
│   ├── blender/              # .blend motion graphics templates
│   └── davinci/              # .drp DaVinci project templates
├── output/                   # Final renders
├── cache/                    # TTS, API, processing cache
├── logs/                     # Pipeline logs
├── state/                    # Persistent queue state
├── models/
│   └── rife/                 # RIFE v4.6 model weights
├── monitoring/               # Prometheus/Grafana configs
├── scripts/                  # Generated DaVinci/Blender scripts
├── backups/                  # Automated backups
├── deploy.sh                 # VPS deployment script
├── manage.sh                 # Local management script
├── Dockerfile                # Multi-stage Docker build
├── docker-compose.yml        # Multi-service orchestration
├── requirements.txt          # Python dependencies
└── README.md                 # This file
```

---

## 🔧 Advanced Usage

### Custom Research Topics
```python
from skills.orchestrator import SpaceExplorationOrchestrator, Topic

orchestrator = await SpaceExplorationOrchestrator()

topic = Topic(
    id="custom_001",
    title="Why Starship Changes Everything",
    pillar="space_technology",
    priority=10,
    video_type="deep_dive",
    target_duration=600,
    tone="cinematic"
)

orchestrator.add_topic(topic)
result = await orchestrator.run_full_pipeline(topic)
```

### Custom VFX Templates
Add `.blend` files to `templates/blender/` with naming:
- `cosmic_odyssey_orbital.blend` - Orbital mechanics
- `nature_reimagined_earth.blend` - Earth from space
- `urban_cyberpunk_station.blend` - Space stations
- `abstract_art_data_viz.blend` - Data visualization
- `vintage_restored_archive.blend` - Historical footage

### Pronunciation Dictionary
Edit `config/pronunciation.json`:
```json
{
  "artemis": "AA R T AH M IH S",
  "jwst": "JEY D AH B AH L Y UW S P EY S T EH L",
  "your_term": "PHONEMES"
}
```

---

## 📈 Monitoring & Analytics

### Prometheus Metrics (port 9090)
- `orchestrator_topics_total` - Total topics in queue
- `orchestrator_topics_by_status` - Topics per status
- `orchestrator_pipeline_success_rate` - Success percentage
- `orchestrator_stage_duration_seconds` - Per-stage timing
- `orchestrator_videos_published_total` - Cumulative videos
- `orchestrator_active_jobs` - Currently running
- `orchestrator_cache_hit_rate` - Cache efficiency

### Grafana Dashboard (port 3000)
Pre-built dashboard at `monitoring/grafana/dashboards/pipeline.json` with:
- Topic queue status
- Pipeline success rate
- Stage durations
- Videos published
- Job statistics
- Storage usage
- API call rates
- Cache performance

---

## 🚨 Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `elevenlabs_tts` fails | Check API key, quota, voice_id exists |
| `nasa_footage` downloads fail | Verify NASA API key, network, disk space |
| `motion_graphics` Blender errors | Check Blender path, template exists, GPU memory |
| `compositing` DaVinci fails | Verify DaVinci path, project template, media pool |
| YouTube upload fails | Check OAuth token, quota, video format |
| RIFE interpolation slow | Enable GPU, reduce scale_factor, check model path |

### Debug Mode
```bash
# Verbose logging
LOG_LEVEL=DEBUG ./manage.sh daily

# Test single skill with debug
./manage.sh test nasa_research --topic "Mars" --debug
```

### Logs Location
- Local: `logs/pipeline.log`
- Docker: `docker-compose logs -f orchestrator`
- Systemd: `journalctl -u space-exploration -f`

---

## 🤝 Contributing

1. Fork the repository
2. Create feature branch: `git checkout -b feature/amazing-feature`
3. Add tests for new skills
4. Ensure `black`, `isort`, `flake8` pass
5. Submit PR with detailed description

### Adding New Skills
```python
# 1. Create skill module in skills/
# 2. Inherit from BaseSkill
# 3. Define metadata with category
# 4. Register in skills/__init__.py
# 5. Add to appropriate pipeline in orchestrator.py
```

---

## 📄 License

MIT License - See LICENSE file for details.

**Important**: This automation system is for educational and legitimate content creation purposes. Users are responsible for:
- Complying with YouTube Terms of Service
- Respecting API rate limits and terms
- Ensuring all content uses properly licensed sources
- Following FTC disclosure guidelines for sponsorships

---

## 🙏 Acknowledgments

- **NASA** - Public domain imagery and data
- **ElevenLabs** - Best-in-class TTS
- **Blackmagic Design** - DaVinci Resolve
- **Blender Foundation** - Blender 3D
- **RIFE Authors** - Frame interpolation
- **Space Community** - Inspiration and feedback

---

## 📞 Support

- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions
- **Documentation**: This README + code docs
- **Email**: hello@spaceexplained.com (configure in orchestrator.yaml)

---

**Built with ❤️ for the space exploration community**

*To the stars through automation* 🚀✨