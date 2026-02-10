from app import db
from sqlalchemy.ext.automap import automap_base
from sqlalchemy import Table

def initialize_database():
    """Dynamically load database models using automap."""
    with db.engine.connect() as conn:
        Base = automap_base()
        Base.prepare(autoload_with=db.engine)

        global Queues, Logs, Triggers, SingleTriggers, ScheduledTriggers, QueueTriggers, Credentials, Constants, Schedulers

        Queues = Base.classes.get("Queues")
        Logs = Base.classes.get("Logs")
        Triggers = Base.classes.get("Triggers")
        SingleTriggers = Base.classes.get("Single_Triggers")
        ScheduledTriggers = Base.classes.get("Scheduled_Triggers")
        QueueTriggers = Base.classes.get("Queue_Triggers")
        Credentials = Base.classes.get("Credentials") 
        Constants = Base.classes.get("Constants")
        Schedulers = Base.classes.get("Schedulers")

        # Hjælpetabeller: IKKE automap (ingen relations, ingen antagelser)
        global queue_handled_t, log_viewed_t
        queue_handled_t = Table("queue_handled", db.metadata, schema="dbo", autoload_with=db.engine, extend_existing=True)
        log_viewed_t = Table("log_viewed", db.metadata, schema="dbo", autoload_with=db.engine, extend_existing=True)
