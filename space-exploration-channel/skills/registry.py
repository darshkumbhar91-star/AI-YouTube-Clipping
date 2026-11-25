"""
Skill Registry - Central registry for all automation skills.
Handles discovery, registration, validation, and dependency resolution.
"""

import asyncio
import inspect
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Type, Callable
import importlib
import yaml


logger = logging.getLogger(__name__)


class SkillCategory(Enum):
    """Categories of skills in the automation pipeline."""
    RESEARCH = "research"
    SCRIPT = "script"
    VFX = "vfx"
    VOICE = "voice"
    CHANNEL = "channel"
    OPTIMIZATION = "optimization"
    UTILITY = "utility"


@dataclass
class SkillMetadata:
    """Metadata for a registered skill."""
    name: str
    category: SkillCategory
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    dependencies: List[str] = field(default_factory=list)
    required_config: List[str] = field(default_factory=list)
    optional_config: List[str] = field(default_factory=list)
    inputs: List[str] = field(default_factory=list)
    outputs: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "category": self.category.value,
            "version": self.version,
            "description": self.description,
            "author": self.author,
            "dependencies": self.dependencies,
            "required_config": self.required_config,
            "optional_config": self.optional_config,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "tags": self.tags,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class BaseSkill(ABC):
    """Abstract base class for all skills."""
    
    metadata: SkillMetadata
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.logger = logging.getLogger(f"skill.{self.metadata.name}")
        self._validate_config()
    
    def _validate_config(self):
        """Validate required configuration is present."""
        missing = [key for key in self.metadata.required_config if key not in self.config]
        if missing:
            raise ValueError(f"Skill {self.metadata.name} missing required config: {missing}")
    
    @abstractmethod
    async def execute(self, context: "ExecutionContext") -> Dict[str, Any]:
        """Execute the skill with given context. Must be implemented by subclasses."""
        pass
    
    async def pre_execute(self, context: "ExecutionContext") -> bool:
        """Pre-execution hook. Return False to skip execution."""
        return True
    
    async def post_execute(self, context: "ExecutionContext", result: Dict[str, Any]) -> Dict[str, Any]:
        """Post-execution hook. Can modify result."""
        return result
    
    def get_required_inputs(self) -> List[str]:
        return self.metadata.inputs
    
    def get_outputs(self) -> List[str]:
        return self.metadata.outputs


class SkillRegistry:
    """Central registry for skill discovery and management."""
    
    def __init__(self):
        self._skills: Dict[str, Type[BaseSkill]] = {}
        self._instances: Dict[str, BaseSkill] = {}
        self._metadata: Dict[str, SkillMetadata] = {}
        self._categories: Dict[SkillCategory, Set[str]] = {cat: set() for cat in SkillCategory}
        self._dependency_graph: Dict[str, Set[str]] = {}
    
    def register(self, skill_class: Type[BaseSkill], metadata: Optional[SkillMetadata] = None) -> str:
        """Register a skill class."""
        if metadata is None:
            if not hasattr(skill_class, 'metadata'):
                raise ValueError(f"Skill {skill_class.__name__} must have metadata attribute")
            metadata = skill_class.metadata
        
        name = metadata.name
        
        if name in self._skills:
            logger.warning(f"Overwriting existing skill: {name}")
        
        self._skills[name] = skill_class
        self._metadata[name] = metadata
        self._categories[metadata.category].add(name)
        self._dependency_graph[name] = set(metadata.dependencies)
        
        logger.info(f"Registered skill: {name} ({metadata.category.value}) v{metadata.version}")
        return name
    
    def unregister(self, name: str) -> bool:
        """Unregister a skill."""
        if name not in self._skills:
            return False
        
        metadata = self._metadata[name]
        self._skills.pop(name)
        self._metadata.pop(name)
        self._categories[metadata.category].discard(name)
        self._dependency_graph.pop(name, None)
        self._instances.pop(name, None)
        
        logger.info(f"Unregistered skill: {name}")
        return True
    
    def get_skill_class(self, name: str) -> Optional[Type[BaseSkill]]:
        """Get skill class by name."""
        return self._skills.get(name)
    
    def get_metadata(self, name: str) -> Optional[SkillMetadata]:
        """Get skill metadata by name."""
        return self._metadata.get(name)
    
    def get_instance(self, name: str, config: Optional[Dict[str, Any]] = None) -> Optional[BaseSkill]:
        """Get or create skill instance."""
        if name not in self._skills:
            return None
        
        if name not in self._instances or config is not None:
            skill_class = self._skills[name]
            self._instances[name] = skill_class(config)
        
        return self._instances[name]
    
    def list_skills(self, category: Optional[SkillCategory] = None) -> List[str]:
        """List all registered skills, optionally filtered by category."""
        if category:
            return list(self._categories.get(category, set()))
        return list(self._skills.keys())
    
    def list_by_category(self) -> Dict[str, List[str]]:
        """List all skills grouped by category."""
        return {cat.value: list(skills) for cat, skills in self._categories.items()}
    
    def resolve_dependencies(self, skill_names: List[str]) -> List[str]:
        """Resolve execution order based on dependencies (topological sort)."""
        visited = set()
        temp = set()
        order = []
        
        def visit(name: str):
            if name in temp:
                raise ValueError(f"Circular dependency detected involving {name}")
            if name in visited:
                return
            
            temp.add(name)
            for dep in self._dependency_graph.get(name, set()):
                if dep in self._skills:
                    visit(dep)
            temp.remove(name)
            visited.add(name)
            order.append(name)
        
        for name in skill_names:
            if name in self._skills:
                visit(name)
        
        return order
    
    def validate_dependencies(self, skill_names: List[str]) -> List[str]:
        """Check if all dependencies are registered. Returns missing dependencies."""
        missing = []
        for name in skill_names:
            if name not in self._skills:
                missing.append(name)
                continue
            metadata = self._metadata[name]
            for dep in metadata.dependencies:
                if dep not in self._skills:
                    missing.append(dep)
        return list(set(missing))
    
    async def load_from_directory(self, directory: Path, config: Optional[Dict[str, Any]] = None):
        """Auto-discover and load skills from a directory."""
        for py_file in directory.glob("**/*_skill.py"):
            if py_file.name == "__init__.py":
                continue
            
            try:
                module_path = py_file.relative_to(directory.parent).with_suffix("")
                module_name = ".".join(module_path.parts)
                
                module = importlib.import_module(module_name)
                
                for attr_name in dir(module):
                    attr = getattr(module, attr_name)
                    if (inspect.isclass(attr) and 
                        issubclass(attr, BaseSkill) and 
                        attr is not BaseSkill and
                        hasattr(attr, 'metadata')):
                        self.register(attr)
                        
            except Exception as e:
                logger.error(f"Failed to load skill from {py_file}: {e}")
    
    def export_registry(self, path: Path):
        """Export registry state to YAML."""
        data = {
            "skills": {name: meta.to_dict() for name, meta in self._metadata.items()},
            "categories": {cat.value: list(skills) for cat, skills in self._categories.items()},
            "dependencies": {name: list(deps) for name, deps in self._dependency_graph.items()},
        }
        with open(path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False)
    
    @classmethod
    def import_registry(cls, path: Path, config: Optional[Dict[str, Any]] = None) -> "SkillRegistry":
        """Import registry from YAML."""
        registry = cls()
        with open(path) as f:
            data = yaml.safe_load(f)
        
        for name, meta_dict in data.get("skills", {}).items():
            metadata = SkillMetadata(**meta_dict)
            # Note: Classes would need to be registered separately
            registry._metadata[name] = metadata
            registry._categories[metadata.category].add(name)
            registry._dependency_graph[name] = set(meta_dict.get("dependencies", []))
        
        return registry


# Global registry instance
_global_registry: Optional[SkillRegistry] = None


def get_registry() -> SkillRegistry:
    """Get global skill registry."""
    global _global_registry
    if _global_registry is None:
        _global_registry = SkillRegistry()
    return _global_registry


def register_skill(skill_class: Type[BaseSkill], metadata: Optional[SkillMetadata] = None) -> str:
    """Register a skill in the global registry."""
    return get_registry().register(skill_class, metadata)