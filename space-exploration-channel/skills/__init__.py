"""
Space Exploration Channel - Skill Framework
Core infrastructure for modular, composable automation skills.
"""

from .registry import SkillRegistry, SkillMetadata, SkillCategory
from .pipeline import SkillPipeline, PipelineContext, PipelineStage
from .context import SkillContext, ExecutionContext, ResourceManager
from .modifier import SkillModifier, ModifierChain, ModifierType

__all__ = [
    "SkillRegistry",
    "SkillMetadata", 
    "SkillCategory",
    "SkillPipeline",
    "PipelineContext",
    "PipelineStage",
    "SkillContext",
    "ExecutionContext",
    "ResourceManager",
    "SkillModifier",
    "ModifierChain",
    "ModifierType",
]

__version__ = "1.0.0"