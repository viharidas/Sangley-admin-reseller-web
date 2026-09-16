from dotenv import load_dotenv
from pathlib import Path
load_dotenv(Path(__file__).parent / '.env')
import os
from motor.motor_asyncio import AsyncIOMotorClient
from datetime import datetime, timezone
import uuid

client = AsyncIOMotorClient(os.environ['MONGO_URL'])
db = client[os.environ['DB_NAME']]
def now():
    return datetime.now(timezone.utc).isoformat()
def uid():
    return str(uuid.uuid4())