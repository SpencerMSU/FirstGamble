from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="FirstGamble API", version="0.0.1")

# CORS (потом подправим)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- сюда позже подключим подразделы ---
# from api.routers.ludka import router as ludka_router
# from api.routers.prices import router as prices_router
# from api.routers.rpg import router as rpg_router
# from api.routers.shop import router as shop_router
# from api.routers.raffle import router as raffle_router
# from api.routers.profile import router as profile_router
#
# app.include_router(ludka_router)
# app.include_router(prices_router)
# app.include_router(rpg_router)
# app.include_router(shop_router)
# app.include_router(raffle_router)
# app.include_router(profile_router)

@app.get("/health")
async def health():
    return {"ok": True, "status": "alive"}
