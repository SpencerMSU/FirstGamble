from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from firstgamble_api import app

# Mount static files to serve HTML
app.mount("/cabinet", StaticFiles(directory="cabinet"), name="cabinet")
app.mount("/community", StaticFiles(directory="community"), name="community")
app.mount("/", StaticFiles(directory=".", html=True), name="root") # serve other files

from firstgamble_api.chat import chat_manager

@app.on_event("startup")
async def startup_event():
    await chat_manager.start_redis_listener()

@app.on_event("shutdown")
async def shutdown_event():
    await chat_manager.stop_redis_listener()
