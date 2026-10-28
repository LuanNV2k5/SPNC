from app.db.base import Base
from .user import User, RoleEnum, AccountStatus, RefreshSession, SystemSetting, AuditLog
from .class_org import Class, ClassMembership
from .problem import Problem, ProblemVisibility, SupportedLanguage, ProblemTestCase, ProblemClassPublication
from .exam import Exam, ExamStatus, ParticipationStatus, ExamProblem, ExamAssignment, ExamParticipation
from .session import CodingSession, SessionStatus, TerminationSource, PracticeAttempt
from .trace import TraceEvent, TraceEventType, CodeSnapshot, SnapshotReason
from .run_submit import Run, RunStatus, RunVerdict, Submission, SubmissionSource
from .observation import AttentionSignal, SignalType, SignalStatus, TeacherAnnotation, PointTransaction, TraceSignalOutbox

# Ensure all models are loaded before Alembic reads Base.metadata
__all__ = [
    "Base",
    "User", "RoleEnum", "AccountStatus", "RefreshSession", "SystemSetting", "AuditLog",
    "Class", "ClassMembership",
    "Problem", "ProblemVisibility", "SupportedLanguage", "ProblemTestCase", "ProblemClassPublication",
    "Exam", "ExamStatus", "ParticipationStatus", "ExamProblem", "ExamAssignment", "ExamParticipation",
    "CodingSession", "SessionStatus", "TerminationSource", "PracticeAttempt",
    "TraceEvent", "TraceEventType", "CodeSnapshot", "SnapshotReason",
    "Run", "RunStatus", "RunVerdict", "Submission", "SubmissionSource",
    "AttentionSignal", "SignalType", "SignalStatus", "TeacherAnnotation", "PointTransaction",
    "TraceSignalOutbox",
]
