# engine/rules_yaml_loader.py
"""
YAML规则配置加载器
支持多文档、Profile筛选、别名匹配、版本管理和热更新
"""

import hashlib
import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


@dataclass
class RuleConfig:
    """单个规则配置"""

    id: str
    name: str
    version: str
    severity: str
    enabled: bool
    profile: Optional[str] = None
    aliases: List[str] = field(default_factory=list)
    parameters: Dict[str, Any] = field(default_factory=dict)
    description: str = ""


@dataclass
class ProfileConfig:
    """Profile配置"""

    name: str
    version: str
    enabled_rules: List[str]
    disabled_rules: List[str] = field(default_factory=list)
    rule_overrides: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    description: str = ""


@dataclass
class YamlRulesConfig:
    """完整的YAML规则配置"""

    version: str
    schema_version: str
    last_updated: str
    rules: Dict[str, RuleConfig]
    profiles: Dict[str, ProfileConfig]
    global_settings: Dict[str, Any] = field(default_factory=dict)


class RulesYamlLoader:
    """YAML规则配置加载器"""

    def __init__(self, config_dir: str = "config/rules"):
        self.config_dir = Path(config_dir)
        self.config_dir.mkdir(parents=True, exist_ok=True)

        # 缓存相关
        self._cached_config: Optional[YamlRulesConfig] = None
        self._cache_timestamp: Optional[float] = None
        self._file_hashes: Dict[str, str] = {}

        # 支持的版本和文件
        self.version_files = {
            "v3_3": "rules_v3_3.yaml",
            "v3_3_r2": "rules_v3_3_r2.yaml",
            "v3_4": "rules_v3_4.yaml",
        }

        logger.info(f"Rules YAML loader initialized, config_dir: {self.config_dir}")

    def load_rules_yaml(
        self, version: str = "v3_3", profile: Optional[str] = None, force_reload: bool = False
    ) -> YamlRulesConfig:
        """
        加载YAML规则配置

        Args:
            version: 规则版本 (v3_3, v3_3_r2, v3_4等)
            profile: 指定Profile名称，None表示加载所有
            force_reload: 强制重新加载，忽略缓存

        Returns:
            YAML规则配置对象
        """
        if not force_reload and self._should_use_cache():
            logger.debug("使用缓存的YAML配置")
            if self._cached_config is not None:
                return self._cached_config

        logger.info(f"加载YAML规则配置: version={version}, profile={profile}")

        try:
            # 1. 加载主配置文件
            config = self._load_version_config(version)

            # 2. 合并多文档（如果存在）
            config = self._merge_multi_documents(config, version)

            # 3. 应用Profile筛选
            if profile:
                config = self._apply_profile_filter(config, profile)

            # 4. 处理别名匹配
            config = self._resolve_aliases(config)

            # 5. 验证配置完整性
            self._validate_config(config)

            # 6. 更新缓存
            self._update_cache(config)

            logger.info(
                f"成功加载YAML配置: {len(config.rules)}个规则, {len(config.profiles)}个Profile"
            )
            return config

        except Exception as e:
            logger.error(f"加载YAML配置失败: {e}")
            # 返回默认配置或抛出异常
            if self._cached_config:
                logger.warning("使用缓存配置作为fallback")
                return self._cached_config
            # 创建一个基础的默认配置
            return self._create_fallback_config(version)

    def _load_version_config(self, version: str) -> YamlRulesConfig:
        """加载指定版本的配置文件"""
        if version not in self.version_files:
            raise ValueError(
                f"不支持的版本: {version}, 支持的版本: {list(self.version_files.keys())}"
            )

        config_file = self.config_dir / self.version_files[version]

        if not config_file.exists():
            # 创建默认配置文件
            self._create_default_config(config_file, version)

        with open(config_file, "r", encoding="utf-8") as f:
            yaml_data = yaml.safe_load(f)

        return self._parse_yaml_config(yaml_data)

    def _parse_yaml_config(self, yaml_data: Dict[str, Any]) -> YamlRulesConfig:
        """解析YAML数据为配置对象"""
        # 解析规则
        rules = {}
        for rule_id, rule_data in yaml_data.get("rules", {}).items():
            rules[rule_id] = RuleConfig(
                id=rule_id,
                name=rule_data.get("name", rule_id),
                version=rule_data.get("version", "1.0"),
                severity=rule_data.get("severity", "warn"),
                enabled=rule_data.get("enabled", True),
                profile=rule_data.get("profile"),
                aliases=rule_data.get("aliases", []),
                parameters=rule_data.get("parameters", {}),
                description=rule_data.get("description", ""),
            )

        # 解析Profile
        profiles = {}
        for profile_name, profile_data in yaml_data.get("profiles", {}).items():
            profiles[profile_name] = ProfileConfig(
                name=profile_name,
                version=profile_data.get("version", "1.0"),
                enabled_rules=profile_data.get("enabled_rules", []),
                disabled_rules=profile_data.get("disabled_rules", []),
                rule_overrides=profile_data.get("rule_overrides", {}),
                description=profile_data.get("description", ""),
            )

        return YamlRulesConfig(
            version=yaml_data.get("version", "unknown"),
            schema_version=yaml_data.get("schema_version", "1.0"),
            last_updated=yaml_data.get("last_updated", datetime.now().isoformat()),
            rules=rules,
            profiles=profiles,
            global_settings=yaml_data.get("global_settings", {}),
        )

    def _merge_multi_documents(self, base_config: YamlRulesConfig, version: str) -> YamlRulesConfig:
        """合并多文档配置（如果存在）"""
        # 查找相关的附加配置文件
        additional_files = []
        for file_path in self.config_dir.glob(f"rules_{version}_*.yaml"):
            if file_path.name != self.version_files[version]:
                additional_files.append(file_path)

        if not additional_files:
            return base_config

        logger.info(f"发现{len(additional_files)}个附加配置文件，开始合并")

        # 合并规则和Profile
        for additional_file in additional_files:
            try:
                with open(additional_file, "r", encoding="utf-8") as f:
                    additional_data = yaml.safe_load(f)

                additional_config = self._parse_yaml_config(additional_data)

                # 合并规则
                base_config.rules.update(additional_config.rules)

                # 合并Profile
                base_config.profiles.update(additional_config.profiles)

                # 合并全局设置
                base_config.global_settings.update(additional_config.global_settings)

                logger.debug(f"成功合并配置文件: {additional_file.name}")

            except Exception as e:
                logger.warning(f"合并配置文件{additional_file.name}失败: {e}")

        return base_config

    def _apply_profile_filter(self, config: YamlRulesConfig, profile_name: str) -> YamlRulesConfig:
        """应用Profile筛选"""
        if profile_name not in config.profiles:
            logger.warning(f"Profile '{profile_name}' 不存在，使用完整配置")
            return config

        profile = config.profiles[profile_name]

        # 筛选启用的规则
        filtered_rules = {}
        for rule_id, rule_config in config.rules.items():
            should_include = False

            # 检查是否在启用列表中
            if rule_id in profile.enabled_rules or "*" in profile.enabled_rules:
                should_include = True

            # 检查是否在禁用列表中
            if rule_id in profile.disabled_rules:
                should_include = False

            # 检查Profile匹配
            if rule_config.profile and rule_config.profile == profile_name:
                should_include = True

            if should_include:
                # 应用Profile级别的参数覆盖
                if rule_id in profile.rule_overrides:
                    overrides = profile.rule_overrides[rule_id]
                    for key, value in overrides.items():
                        if hasattr(rule_config, key):
                            setattr(rule_config, key, value)
                        else:
                            rule_config.parameters[key] = value

                # 应用通配符覆盖
                if "*" in profile.rule_overrides:
                    overrides = profile.rule_overrides["*"]
                    for key, value in overrides.items():
                        if hasattr(rule_config, key):
                            setattr(rule_config, key, value)

                filtered_rules[rule_id] = rule_config

        config.rules = filtered_rules
        logger.info(f"Profile筛选完成: {len(filtered_rules)}个规则匹配Profile '{profile_name}'")
        return config

    def _resolve_aliases(self, config: YamlRulesConfig) -> YamlRulesConfig:
        """解析和处理别名匹配"""
        for rule_id, rule_config in config.rules.items():
            if rule_config.aliases:
                # 标准化别名列表
                normalized_aliases = []
                for alias in rule_config.aliases:
                    # 简单的别名标准化处理
                    normalized = alias.strip().lower()
                    if normalized:
                        normalized_aliases.append(normalized)

                rule_config.aliases = normalized_aliases
                logger.debug(f"规则 {rule_id} 处理了 {len(normalized_aliases)} 个别名")

        return config

    def _validate_config(self, config: YamlRulesConfig) -> None:
        """验证配置完整性"""
        errors = []

        # 验证规则
        for rule_id, rule_config in config.rules.items():
            if not rule_config.name:
                errors.append(f"规则 {rule_id} 缺少名称")

            if rule_config.severity not in ["error", "warn", "info"]:
                errors.append(f"规则 {rule_id} 的严重程度无效: {rule_config.severity}")

        # 验证Profile
        for profile_name, profile_config in config.profiles.items():
            # 检查启用的规则是否存在
            for rule_id in profile_config.enabled_rules:
                if rule_id != "*" and rule_id not in config.rules:
                    errors.append(f"Profile {profile_name} 引用了不存在的规则: {rule_id}")

        if errors:
            error_msg = "配置验证失败:\n" + "\n".join(errors)
            raise ValueError(error_msg)

        logger.debug("配置验证通过")

    def _should_use_cache(self) -> bool:
        """检查是否应该使用缓存"""
        if not self._cached_config or not self._cache_timestamp:
            return False

        # 检查文件是否有变化
        current_hashes = self._calculate_file_hashes()
        if current_hashes != self._file_hashes:
            logger.debug("配置文件已更改，需要重新加载")
            return False

        # 检查缓存时间（例如：5分钟内的缓存有效）
        cache_ttl = 300  # 5分钟
        if datetime.now().timestamp() - self._cache_timestamp > cache_ttl:
            logger.debug("缓存已过期")
            return False

        return True

    def _update_cache(self, config: YamlRulesConfig) -> None:
        """更新缓存"""
        self._cached_config = config
        self._cache_timestamp = datetime.now().timestamp()
        self._file_hashes = self._calculate_file_hashes()
        logger.debug("配置缓存已更新")

    def _calculate_file_hashes(self) -> Dict[str, str]:
        """计算配置文件的哈希值"""
        hashes = {}
        for file_path in self.config_dir.glob("*.yaml"):
            try:
                content = file_path.read_bytes()
                hash_value = hashlib.md5(content).hexdigest()
                hashes[str(file_path)] = hash_value
            except Exception as e:
                logger.warning(f"计算文件哈希失败 {file_path}: {e}")
        return hashes

    def _create_default_config(self, config_file: Path, version: str) -> None:
        """创建默认配置文件"""
        default_config = {
            "version": version,
            "schema_version": "1.0",
            "last_updated": datetime.now().isoformat(),
            "global_settings": {"timeout": 120, "max_issues": 50, "enable_debug": False},
            "profiles": {
                "default": {
                    "version": "1.0",
                    "description": "默认Profile，包含所有基础规则",
                    "enabled_rules": ["*"],
                    "disabled_rules": [],
                },
                "strict": {
                    "version": "1.0",
                    "description": "严格模式，启用所有检查项",
                    "enabled_rules": ["*"],
                    "disabled_rules": [],
                    "rule_overrides": {"*": {"severity": "error"}},
                },
                "minimal": {
                    "version": "1.0",
                    "description": "最小模式，仅基础检查",
                    "enabled_rules": ["V33-001", "V33-002", "V33-003"],
                },
            },
            "rules": {
                "V33-001": {
                    "name": "封面年度单位检查",
                    "version": "1.0",
                    "severity": "warn",
                    "enabled": True,
                    "description": "检查封面年度和单位信息的完整性",
                    "aliases": ["封面检查", "年度检查", "单位检查"],
                    "parameters": {"require_year": True, "require_unit": True},
                },
                "V33-002": {
                    "name": "九张表齐全性检查",
                    "version": "1.0",
                    "severity": "error",
                    "enabled": True,
                    "description": "检查九张预算表是否齐全",
                    "aliases": ["九张表", "表格齐全性"],
                    "parameters": {
                        "required_tables": [
                            "收入支出决算总表",
                            "收入决算表",
                            "支出决算表",
                            "财政拨款收入支出决算总表",
                            "一般公共预算财政拨款支出决算表",
                            "一般公共预算财政拨款基本支出决算表",
                            "一般公共预算财政拨款三公经费支出决算表",
                            "政府性基金预算财政拨款收入支出决算表",
                            "国有资本经营预算财政拨款支出决算表",
                        ],
                        "min_required": 6,
                    },
                },
                "V33-003": {
                    "name": "页面文件阈值检查",
                    "version": "1.0",
                    "severity": "warn",
                    "enabled": True,
                    "description": "检查文件页数和大小是否合理",
                    "parameters": {"max_pages": 200, "max_file_size_mb": 50, "min_pages": 5},
                },
            },
        }

        with open(config_file, "w", encoding="utf-8") as f:
            yaml.dump(
                default_config, f, default_flow_style=False, allow_unicode=True, sort_keys=False
            )

        logger.info(f"创建默认配置文件: {config_file}")

    def _create_fallback_config(self, version: str) -> YamlRulesConfig:
        """创建fallback配置"""
        return YamlRulesConfig(
            version=version,
            schema_version="1.0",
            last_updated=datetime.now().isoformat(),
            rules={},
            profiles={},
        )

    def reload_config(
        self, version: str = "v3_3", profile: Optional[str] = None
    ) -> YamlRulesConfig:
        """热更新配置"""
        logger.info(f"热更新规则配置: version={version}, profile={profile}")
        return self.load_rules_yaml(version, profile, force_reload=True)

    def get_available_versions(self) -> List[str]:
        """获取可用的版本列表"""
        available = []
        for version, filename in self.version_files.items():
            config_file = self.config_dir / filename
            if config_file.exists():
                available.append(version)
        return available

    def get_available_profiles(self, version: str = "v3_3") -> List[str]:
        """获取指定版本的可用Profile列表"""
        try:
            config = self.load_rules_yaml(version)
            return list(config.profiles.keys())
        except Exception as e:
            logger.error(f"获取Profile列表失败: {e}")
            return []


# 全局实例
_rules_loader_instance: Optional[RulesYamlLoader] = None


def get_rules_loader() -> RulesYamlLoader:
    """获取全局规则加载器实例"""
    global _rules_loader_instance
    if _rules_loader_instance is None:
        config_dir = os.getenv("RULES_CONFIG_DIR", "config/rules")
        _rules_loader_instance = RulesYamlLoader(config_dir)
    return _rules_loader_instance


def load_rules_yaml(version: str = "v3_3", profile: Optional[str] = None) -> YamlRulesConfig:
    """便捷函数：加载YAML规则配置"""
    loader = get_rules_loader()
    return loader.load_rules_yaml(version, profile)
