from app import db
from sqlalchemy.ext.automap import automap_base

def initialize_database():
    """Dynamically load database models using automap."""
    with db.engine.connect() as conn:
        Base = automap_base()
        Base.prepare(autoload_with=db.engine)

        global Queues, Logs, Triggers, SingleTriggers, ScheduledTriggers, QueueTriggers, Credentials, Constants
        Queues = Base.classes.get("Queues")
        Logs = Base.classes.get("Logs")
        Triggers = Base.classes.get("Triggers")
        SingleTriggers = Base.classes.get("Single_Triggers")
        ScheduledTriggers = Base.classes.get("Scheduled_Triggers")
        QueueTriggers = Base.classes.get("Queue_Triggers")
        Credentials = Base.classes.get("Credentials") 
        Constants = Base.classes.get("Constants")
