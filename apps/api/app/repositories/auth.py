import uuid

from typing import Optional, List

from sqlalchemy.orm import Session

from sqlalchemy import select, update



from app.models.user import User, RefreshSession



def get_user_by_username(db: Session, username: str) -> Optional[User]:

    return db.execute(select(User).where(User.username == username)).scalar_one_or_none()



def get_user_by_id(db: Session, user_id: uuid.UUID) -> Optional[User]:

    return db.execute(select(User).where(User.id == user_id)).scalar_one_or_none()



def create_refresh_session(db: Session, user_id: uuid.UUID, family_id: uuid.UUID, token_hash: str, expires_at) -> RefreshSession:

    db_session = RefreshSession(

        user_id=user_id,

        family_id=family_id,

        token_hash=token_hash,

        expires_at=expires_at

    )

    db.add(db_session)

    db.commit()

    db.refresh(db_session)

    return db_session



def get_refresh_session_by_hash(db: Session, token_hash: str) -> Optional[RefreshSession]:

    return db.execute(

        select(RefreshSession).where(RefreshSession.token_hash == token_hash)

    ).scalar_one_or_none()



def revoke_refresh_session(db: Session, session_id: uuid.UUID):

    db.execute(

        update(RefreshSession).where(RefreshSession.id == session_id).values(is_revoked=True)

    )

    db.commit()



def revoke_refresh_family(db: Session, family_id: uuid.UUID):

    db.execute(

        update(RefreshSession).where(RefreshSession.family_id == family_id).values(is_revoked=True)

    )

    db.commit()



def revoke_all_user_sessions(db: Session, user_id: uuid.UUID):

    db.execute(

        update(RefreshSession).where(RefreshSession.user_id == user_id).values(is_revoked=True)

    )

    db.commit()
