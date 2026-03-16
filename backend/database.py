#sqlalchemy ka engine or session ek baar
#yha bnao-pore project m import kro
# baar baar connection bnana expensive hota h
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
from backend.config import DATABASE_URL

#engine-actual db connection
# check_same_thread sirf SQLite ke liye zaroori hai
# PostgreSQL pe jaao toh ye argument automatically ignore hoga
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread":False} if "sqlite" in DATABASE_URL else {}

)
#session factory-har request k liye ek session
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,   #manually comit kro
    autoflush=False     #manually flush kro
)
#base-sb models ise hi inherit krnge
Base = declarative_base()

def get_db():
    """FastAPI for the dependency.
    Every API request needs its own session.
    Request over ->session over
    Why dependency injection?
    ->Connection wont leak
    ->easily mock in test
    ->every request stays isolated
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Create tables even if they dont exist.
    Will be called once app starts"""
    #sb models import kro taki base ko pth ho
    from backend.models import user, company, contact, application, reply
    Base.metadata.create_all(bind=engine)
    print("Database initialized")
