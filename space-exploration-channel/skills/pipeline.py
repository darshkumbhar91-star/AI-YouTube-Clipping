"""
Skill Pipeline - Orchestrates skill execution with stages, checkpoints, and error handling.
"""

import asyncio
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set
from contextlib import asynccontextmanager

from .registry import SkillRegistry, BaseSkill, SkillMetadata, get_registry


logger = logging.getLogger(__name__)


class PipelineStage(Enum):
    """Stages in the content production pipeline."""
    INIT = "init"
    RESEARCH = "research"
    SCRIPT = "script"
    VFX_PREP = "vfx_prep"
    VFX_RENDER = "vfx_render"
    VOICE = "voice"
    COMPOSITE = "composite"
    OPTIMIZE = "optimize"
    UPLOAD = "upload"
    PUBLISH = "publish"
    ANALYTICS = "analytics"
    COMPLETE = "complete"
    FAILED = "failed"


@dataclass
class PipelineContext:
    """Context passed through pipeline stages."""
    pipeline_id: str
    topic_id: str
    topic_data: Dict[str, Any] = field(default_factory=dict)
    stage: PipelineStage = PipelineStage.INIT
    stage_history: List[Dict[str, Any]] = field(default_factory=list)
    artifacts: Dict[str, Any] = field(default_factory=dict)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    checkpoint_data: Dict[str, Any] = field(default_factory=dict)
    
    def add_artifact(self, key: str, value: Any):
        self.artifacts[key] = value
        self.updated_at = datetime.now().isoformat()
    
    def get_artifact(self, key: str, default: Any = None) -> Any:
        return self.artifacts.get(key, default)
    
    def add_error(self, stage: PipelineStage, error: Exception, fatal: bool = False):
        self.errors.append({
            "stage": stage.value,
            "error": str(error),
            "type": type(error).__name__,
            "fatal": fatal,
            "timestamp": datetime.now().isoformat()
        })
    
    def add_warning(self, message: str):
        self.warnings.append(message)
        self.updated_at = datetime.now().isoformat()
    
    def advance_stage(self, stage: PipelineStage):
        self.stage_history.append({
            "stage": self.stage.value,
            "completed_at": datetime.now().isoformat(),
            "artifacts_count": len(self.artifacts)
        })
        self.stage = stage
        self.updated_at = datetime.now().isoformat()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_id": self.pipeline_id,
            "topic_id": self.topic_id,
            "topic_data": self.topic_data,
            "stage": self.stage.value,
            "stage_history": self.stage_history,
            "artifacts": {k: str(v) for k, v in self.artifacts.items()},
            "errors": self.errors,
            "warnings": self.warnings,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


@dataclass
class ExecutionContext:
    """Execution context for individual skill runs."""
    skill_name: str
    pipeline_context: PipelineContext
    config: Dict[str, Any]
    resources: Dict[str, Any] = field(default_factory=dict)
    start_time: str = field(default_factory=lambda: datetime.now().isoformat())
    attempt: int = 1
    max_attempts: int = 3
    
    def get_input(self, key: str, default: Any = None) -> Any:
        return self.pipeline_context.get_artifact(key, default)
    
    def set_output(self, key: str, value: Any):
        self.pipeline_context.add_artifact(key, value)
    
    def get_config(self, key: str, default: Any = None) -> Any:
        return self.config.get(key, default)


class SkillPipeline:
    """Orchestrates multi-skill pipelines with checkpointing and recovery."""
    
    def __init__(
        self,
        name: str,
        skills: List[str],
        registry: Optional[SkillRegistry] = None,
        config: Optional[Dict[str, Any]] = None,
        checkpoint_dir: Optional[Path] = None
    ):
        self.name = name
        self.skill_names = skills
        self.registry = registry or get_registry()
        self.config = config or {}
        self.checkpoint_dir = checkpoint_dir or Path("checkpoints")
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        
        self._stage_map: Dict[PipelineStage, List[str]] = {}
        self._skill_stages: Dict[str, PipelineStage] = {}
        self._hooks: Dict[str, List[Callable]] = {
            "pre_pipeline": [],
            "post_pipeline": [],
            "pre_stage": [],
            "post_stage": [],
            "on_error": [],
            "on_checkpoint": [],
        }
        
        self._build_stage_map()
        self._validate_pipeline()
    
    def _build_stage_map(self):
        """Map skills to pipeline stages based on their categories."""
        stage_order = [
            PipelineStage.RESEARCH,
            PipelineStage.SCRIPT,
            PipelineStage.VFX_PREP,
            PipelineStage.VFX_RENDER,
            PipelineStage.VOICE,
            PipelineStage.COMPOSITE,
            PipelineStage.OPTIMIZE,
            PipelineStage.UPLOAD,
            PipelineStage.PUBLISH,
            PipelineStage.ANALYTICS,
        ]
        
        category_to_stage = {
            "research": PipelineStage.RESEARCH,
            "script": PipelineStage.SCRIPT,
            "vfx": PipelineStage.VFX_PREP,  # Will split prep/render later
            "voice": PipelineStage.VOICE,
            "channel": PipelineStage.UPLOAD,
            "optimization": PipelineStage.OPTIMIZE,
        }
        
        for skill_name in self.skill_names:
            metadata = self.registry.get_metadata(skill_name)
            if not metadata:
                logger.warning(f"Skill {skill_name} not found in registry")
                continue
            
            stage = category_to_stage.get(metadata.category.value, PipelineStage.INIT)
            if stage not in self._stage_map:
                self._stage_map[stage] = []
            self._stage_map[stage].append(skill_name)
            self._skill_stages[skill_name] = stage
    
    def _validate_pipeline(self):
        """Validate pipeline configuration."""
        missing = self.registry.validate_dependencies(self.skill_names)
        if missing:
            raise ValueError(f"Missing dependencies: {missing}")
        
        # Check for circular dependencies
        try:
            self.registry.resolve_dependencies(self.skill_names)
        except ValueError as e:
            raise ValueError(f"Invalid pipeline: {e}")
    
    def add_hook(self, hook_name: str, callback: Callable):
        """Add a pipeline hook."""
        if hook_name in self._hooks:
            self._hooks[hook_name].append(callback)
        else:
            raise ValueError(f"Unknown hook: {hook_name}")
    
    async def execute(
        self,
        topic_id: str,
        topic_data: Dict[str, Any],
        resume_from: Optional[str] = None
    ) -> PipelineContext:
        """Execute the full pipeline."""
        pipeline_id = str(uuid.uuid4())[:8]
        
        # Load checkpoint if resuming
        context = None
        if resume_from:
            context = await self._load_checkpoint(resume_from)
            if context:
                context.pipeline_id = pipeline_id
                logger.info(f"Resuming pipeline {pipeline_id} from checkpoint {resume_from}")
        
        if context is None:
            context = PipelineContext(
                pipeline_id=pipeline_id,
                topic_id=topic_id,
                topic_data=topic_data
            )
        
        logger.info(f"Starting pipeline {self.name} [{pipeline_id}] for topic {topic_id}")
        
        # Execute pre-pipeline hooks
        await self._run_hooks("pre_pipeline", context)
        
        try:
            # Execute stages in order
            stage_order = [
                PipelineStage.RESEARCH,
                PipelineStage.SCRIPT,
                PipelineStage.VFX_PREP,
                PipelineStage.VFX_RENDER,
                PipelineStage.VOICE,
                PipelineStage.COMPOSITE,
                PipelineStage.OPTIMIZE,
                PipelineStage.UPLOAD,
                PipelineStage.PUBLISH,
                PipelineStage.ANALYTICS,
            ]
            
            for stage in stage_order:
                if stage not in self._stage_map:
                    continue
                
                skills_in_stage = self._stage_map[stage]
                if not skills_in_stage:
                    continue
                
                # Check if we should skip completed stages when resuming
                if resume_from and self._is_stage_completed(context, stage):
                    logger.info(f"Skipping completed stage: {stage.value}")
                    continue
                
                await self._execute_stage(context, stage, skills_in_stage)
                
                # Checkpoint after each stage
                await self._save_checkpoint(context)
                await self._run_hooks("on_checkpoint", context)
                
                if context.stage == PipelineStage.FAILED:
                    break
            
            if context.stage != PipelineStage.FAILED:
                context.advance_stage(PipelineStage.COMPLETE)
                logger.info(f"Pipeline {pipeline_id} completed successfully")
        
        except Exception as e:
            logger.exception(f"Pipeline {pipeline_id} failed")
            context.add_error(context.stage, e, fatal=True)
            context.advance_stage(PipelineStage.FAILED)
            await self._run_hooks("on_error", context)
        
        finally:
            await self._run_hooks("post_pipeline", context)
            await self._save_checkpoint(context)
        
        return context
    
    async def _execute_stage(
        self,
        context: PipelineContext,
        stage: PipelineStage,
        skill_names: List[str]
    ):
        """Execute all skills in a stage."""
        context.advance_stage(stage)
        logger.info(f"Executing stage: {stage.value} with skills: {skill_names}")
        
        await self._run_hooks("pre_stage", context, stage)
        
        # Resolve execution order within stage based on dependencies
        execution_order = self.registry.resolve_dependencies(skill_names)
        
        for skill_name in execution_order:
            if skill_name not in skill_names:
                continue
            
            await self._execute_skill(context, skill_name)
            
            if context.stage == PipelineStage.FAILED:
                break
        
        await self._run_hooks("post_stage", context, stage)
    
    async def _execute_skill(self, context: PipelineContext, skill_name: str):
        """Execute a single skill with retry logic."""
        skill = self.registry.get_instance(skill_name, self.config.get(skill_name))
        if not skill:
            raise ValueError(f"Skill {skill_name} not found or failed to instantiate")
        
        exec_context = ExecutionContext(
            skill_name=skill_name,
            pipeline_context=context,
            config=self.config.get(skill_name, {})
        )
        
        logger.info(f"Executing skill: {skill_name}")
        
        for attempt in range(1, exec_context.max_attempts + 1):
            exec_context.attempt = attempt
            try:
                # Pre-execution hook
                if not await skill.pre_execute(exec_context):
                    logger.info(f"Skill {skill_name} pre-execute returned False, skipping")
                    return
                
                # Execute skill
                result = await skill.execute(exec_context)
                
                # Post-execution hook
                result = await skill.post_execute(exec_context, result)
                
                # Store outputs
                for key, value in result.items():
                    context.add_artifact(f"{skill_name}.{key}", value)
                
                logger.info(f"Skill {skill_name} completed successfully")
                return
                
            except Exception as e:
                logger.warning(f"Skill {skill_name} attempt {attempt} failed: {e}")
                if attempt == exec_context.max_attempts:
                    context.add_error(context.stage, e, fatal=True)
                    context.advance_stage(PipelineStage.FAILED)
                    raise
                await asyncio.sleep(2 ** attempt)  # Exponential backoff
    
    def _is_stage_completed(self, context: PipelineContext, stage: PipelineStage) -> bool:
        """Check if a stage was already completed."""
        for entry in context.stage_history:
            if entry["stage"] == stage.value:
                return True
        return False
    
    async def _save_checkpoint(self, context: PipelineContext):
        """Save pipeline checkpoint."""
        checkpoint_file = self.checkpoint_dir / f"{context.pipeline_id}_{context.stage.value}.json"
        import json
        with open(checkpoint_file, 'w') as f:
            json.dump(context.to_dict(), f, indent=2)
        logger.debug(f"Checkpoint saved: {checkpoint_file}")
    
    async def _load_checkpoint(self, checkpoint_id: str) -> Optional[PipelineContext]:
        """Load pipeline checkpoint."""
        import json
        checkpoint_files = list(self.checkpoint_dir.glob(f"{checkpoint_id}_*.json"))
        if not checkpoint_files:
            return None
        
        # Get latest checkpoint
        latest = max(checkpoint_files, key=lambda f: f.stat().st_mtime)
        with open(latest) as f:
            data = json.load(f)
        
        context = PipelineContext(
            pipeline_id=data["pipeline_id"],
            topic_id=data["topic_id"],
            topic_data=data["topic_data"],
            stage=PipelineStage(data["stage"]),
            stage_history=data["stage_history"],
            artifacts=data["artifacts"],
            errors=data["errors"],
            warnings=data["warnings"],
            metadata=data["metadata"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
        )
        return context
    
    async def _run_hooks(self, hook_name: str, *args, **kwargs):
        """Run all callbacks for a hook."""
        for callback in self._hooks.get(hook_name, []):
            try:
                if asyncio.iscoroutinefunction(callback):
                    await callback(*args, **kwargs)
                else:
                    callback(*args, **kwargs)
            except Exception as e:
                logger.error(f"Hook {hook_name} callback failed: {e}")
    
    def get_pipeline_info(self) -> Dict[str, Any]:
        """Get pipeline configuration info."""
        return {
            "name": self.name,
            "skills": self.skill_names,
            "stages": {
                stage.value: skills 
                for stage, skills in self._stage_map.items()
            },
            "skill_stages": self._skill_stages,
        }


class PipelineBuilder:
    """Fluent builder for creating pipelines."""
    
    def __init__(self, name: str, registry: Optional[SkillRegistry] = None):
        self.name = name
        self.registry = registry or get_registry()
        self._skills: List[str] = []
        self._config: Dict[str, Any] = {}
        self._checkpoint_dir: Optional[Path] = None
    
    def add_skill(self, skill_name: str) -> "PipelineBuilder":
        self._skills.append(skill_name)
        return self
    
    def add_skills(self, skill_names: List[str]) -> "PipelineBuilder":
        self._skills.extend(skill_names)
        return self
    
    def with_config(self, config: Dict[str, Any]) -> "PipelineBuilder":
        self._config = config
        return self
    
    def with_checkpoint_dir(self, path: Path) -> "PipelineBuilder":
        self._checkpoint_dir = path
        return self
    
    def build(self) -> SkillPipeline:
        return SkillPipeline(
            name=self.name,
            skills=self._skills,
            registry=self.registry,
            config=self._config,
            checkpoint_dir=self._checkpoint_dir
        )