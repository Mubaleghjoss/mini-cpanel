import uuid
from datetime import datetime
from sqlalchemy import Column, String, Integer, Boolean, DateTime, ForeignKey, CheckConstraint, UniqueConstraint
from sqlalchemy.orm import relationship
from app.core.database import Base

def generate_uuid():
    return str(uuid.uuid4())

class User(Base):
    __tablename__ = "users"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, default="viewer", nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

class Project(Base):
    __tablename__ = "projects"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    provider = Column(String, nullable=False)
    git_repo = Column(String, nullable=True)
    branch = Column(String, nullable=True, default="main")
    port = Column(Integer, nullable=True)
    status = Column(String, default="offline")
    env_vars = Column(String, nullable=True)
    last_deployed = Column(DateTime, nullable=True)
    webhook_secret = Column(String, nullable=True)
    ping_latency_ms = Column(Integer, nullable=True)
    ping_error_detail = Column(String, nullable=True)
    enable_http_ping = Column(Boolean, default=True, nullable=False, server_default="1")
    
    domains = relationship("Domain", back_populates="project", cascade="all, delete-orphan")
    cron_jobs = relationship("CronJob", back_populates="project", cascade="all, delete-orphan")
    backups = relationship("Backup", back_populates="project", cascade="all, delete-orphan")
    logs = relationship("ActivityLog", back_populates="project", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="project", cascade="all, delete-orphan")

class ApplicationInventory(Base):
    __tablename__ = "application_inventory"

    id = Column(String, primary_key=True, default=generate_uuid)
    identity = Column(String, unique=True, index=True, nullable=False)
    display_name = Column(String, nullable=False)
    source_path = Column(String, nullable=True)
    classification = Column(String, nullable=False, default="managed_application")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    environments = relationship(
        "ApplicationEnvironment",
        back_populates="application",
        cascade="all, delete-orphan",
        order_by="ApplicationEnvironment.environment_key",
    )
    operation_contexts = relationship("EnvironmentOperationContext", back_populates="application")

    __table_args__ = (
        CheckConstraint(
            "classification IN ('managed_application', 'development_only', 'system_tool')",
            name="ck_application_inventory_classification",
        ),
    )


class ApplicationEnvironment(Base):
    __tablename__ = "application_environments"

    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(
        String,
        ForeignKey("application_inventory.id", ondelete="CASCADE"),
        nullable=False,
    )
    environment_key = Column(String, nullable=False)
    runtime_path = Column(String, nullable=True)
    branch = Column(String, nullable=True)
    domain = Column(String, nullable=True)
    service_identifier = Column(String, nullable=True)
    read_only_default = Column(
        Boolean,
        nullable=False,
        default=lambda context: context.get_current_parameters().get("environment_key") == "production",
    )

    application = relationship("ApplicationInventory", back_populates="environments")
    operation_contexts = relationship("EnvironmentOperationContext", back_populates="environment")

    __table_args__ = (
        CheckConstraint(
            "environment_key IN ('production', 'staging')",
            name="ck_application_environment_key",
        ),
        UniqueConstraint(
            "project_id",
            "environment_key",
            name="uq_application_environment_project_key",
        ),
    )


class EnvironmentOperationContext(Base):
    """Immutable snapshots reserved for future privileged operation submissions."""

    __tablename__ = "environment_operation_contexts"

    id = Column(String, primary_key=True, default=generate_uuid)
    application_environment_id = Column(
        String,
        ForeignKey("application_environments.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_id = Column(
        String,
        ForeignKey("application_inventory.id", ondelete="RESTRICT"),
        nullable=False,
    )
    application_identity = Column(String, nullable=False)
    environment_key = Column(String, nullable=False)
    target_type = Column(String, nullable=False)
    action_class = Column(String, nullable=False)
    policy_mode = Column(String, nullable=False)
    read_only = Column(Boolean, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    application = relationship("ApplicationInventory", back_populates="operation_contexts")
    environment = relationship("ApplicationEnvironment", back_populates="operation_contexts")

    __table_args__ = (
        CheckConstraint(
            "environment_key IN ('production', 'staging')",
            name="ck_environment_operation_context_environment_key",
        ),
        CheckConstraint(
            "target_type IN ('database_connection', 'backup', 'release')",
            name="ck_environment_operation_context_target_type",
        ),
        CheckConstraint(
            "action_class IN ('registration', 'plan', 'run', 'deploy')",
            name="ck_environment_operation_context_action_class",
        ),
        CheckConstraint(
            "policy_mode IN ('standard', 'read_only')",
            name="ck_environment_operation_context_policy_mode",
        ),
        CheckConstraint(
            "read_only IN (0, 1)",
            name="ck_environment_operation_context_read_only",
        ),
    )


class Domain(Base):
    __tablename__ = "domains"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    domain_name = Column(String, unique=True, nullable=False)
    ssl_enabled = Column(Boolean, default=False)
    ssl_expiry = Column(DateTime, nullable=True)
    ssl_provider = Column(String, nullable=True)
    
    project = relationship("Project", back_populates="domains")

class CronJob(Base):
    __tablename__ = "cron_jobs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(String, nullable=False)
    schedule = Column(String, nullable=False)
    command = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    last_run = Column(DateTime, nullable=True)
    last_output = Column(String, nullable=True)
    
    project = relationship("Project", back_populates="cron_jobs")

class Backup(Base):
    __tablename__ = "backups"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    name = Column(String, nullable=False)
    backup_type = Column(String, nullable=False)
    storage_provider = Column(String, nullable=False)
    file_path = Column(String, nullable=False)
    file_size = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="backups")

class NotificationChannel(Base):
    __tablename__ = "notification_channels"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    channel_type = Column(String, nullable=False)
    webhook_url = Column(String, nullable=True)
    bot_token = Column(String, nullable=True)
    chat_id = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    alert_rules = Column(String, nullable=True)

class ActivityLog(Base):
    __tablename__ = "activity_logs"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    event_type = Column(String, nullable=False)
    message = Column(String, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="logs")


class DatabaseConnection(Base):
    __tablename__ = "database_connections"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    name = Column(String, nullable=False)
    db_type = Column(String, nullable=False)
    host = Column(String, nullable=True)
    port = Column(Integer, nullable=True)
    username = Column(String, nullable=True)
    password = Column(String, nullable=True)
    database_name = Column(String, nullable=True)
    file_path = Column(String, nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    
    key = Column(String, primary_key=True)
    value = Column(String, nullable=False)


class Deployment(Base):
    __tablename__ = "deployments"
    
    id = Column(String, primary_key=True, default=generate_uuid)
    project_id = Column(String, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    commit_sha = Column(String, nullable=True)
    commit_message = Column(String, nullable=True)
    commit_author = Column(String, nullable=True)
    status = Column(String, default="queued")
    build_logs = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    project = relationship("Project", back_populates="deployments")


class IngressRule(Base):
    __tablename__ = "ingress_rules"

    id = Column(String, primary_key=True, default=generate_uuid)
    domain_name = Column(String, unique=True, index=True, nullable=False)
    target_type = Column(String, nullable=False)
    target_value = Column(String, nullable=False)
    max_body_size = Column(String, default="100M", nullable=False)
    cors_enabled = Column(Boolean, default=False, nullable=False)
    ssl_enabled = Column(Boolean, default=False, nullable=False)
    ssl_expiry = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)



