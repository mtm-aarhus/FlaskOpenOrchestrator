from sqlalchemy import select, insert
from app import db
from app.database import queue_handled_t, log_viewed_t

def mark_queue_handled(queue_id):
    db.session.execute(insert(queue_handled_t).values(queue_id=queue_id))

def is_queue_handled(queue_id) -> bool:
    stmt = select(queue_handled_t.c.queue_id).where(queue_handled_t.c.queue_id == queue_id).limit(1)
    return db.session.execute(stmt).first() is not None

def mark_log_viewed(log_id):
    db.session.execute(insert(log_viewed_t).values(log_id=log_id))

def is_log_viewed(log_id) -> bool:
    stmt = select(log_viewed_t.c.log_id).where(log_viewed_t.c.log_id == log_id).limit(1)
    return db.session.execute(stmt).first() is not None
