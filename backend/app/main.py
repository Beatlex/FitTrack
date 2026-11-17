import os
from datetime import datetime, timezone
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from pwdlib import PasswordHash
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from .database import Base, engine, get_db
from .models import FoodEntry, Measurement, User
Base.metadata.create_all(bind=engine)
hasher = PasswordHash.recommended()
app = FastAPI(title="FitTrack API", version="0.1.0")
app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "dev-only-change-this-secret"), same_site="lax", https_only=os.getenv("COOKIE_SECURE", "false").lower() == "true")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    uid=request.session.get("user_id"); user=db.get(User,uid) if uid else None
    if not user: raise HTTPException(401,"Bitte anmelden.")
    return user
@app.get("/api/health")
def health(): return {"status":"ok"}
@app.post("/api/auth/register",status_code=201)
def register(data:dict,db:Session=Depends(get_db)):
    name=str(data.get("username","")).strip().lower(); password=str(data.get("password",""))
    if len(name)<3 or len(name)>40 or len(password)<10: raise HTTPException(400,"Benutzername: 3–40 Zeichen; Passwort: mindestens 10 Zeichen.")
    if db.scalar(select(User).where(User.username==name)): raise HTTPException(409,"Benutzername bereits vergeben.")
    if (db.scalar(select(func.count(User.id))) or 0)>=2: raise HTTPException(403,"Die zwei Konten sind bereits eingerichtet.")
    user=User(username=name,password_hash=hasher.hash(password)); db.add(user); db.commit()
    return {"id":user.id,"username":user.username}
@app.post("/api/auth/login")
def login(data:dict,request:Request,db:Session=Depends(get_db)):
    user=db.scalar(select(User).where(User.username==str(data.get("username","")).strip().lower()))
    if not user or not hasher.verify(str(data.get("password","")),user.password_hash): raise HTTPException(401,"Benutzername oder Passwort falsch.")
    request.session.clear(); request.session["user_id"]=user.id
    return {"id":user.id,"username":user.username}
@app.post("/api/auth/logout")
def logout(request:Request): request.session.clear(); return {"status":"ok"}
@app.get("/api/auth/me")
def me(user:User=Depends(current_user)): return {"id":user.id,"username":user.username}
def m_out(x): return {"id":x.id,"measured_at":x.measured_at.isoformat(),**{k:getattr(x,k) for k in ("weight_kg","waist_cm","chest_cm","hip_cm","arm_cm","thigh_cm")}}
def f_out(x): return {"id":x.id,"consumed_at":x.consumed_at.isoformat(),**{k:getattr(x,k) for k in ("meal_type","food_name","amount_g","calories","protein_g","carbs_g","fat_g")}}
@app.get("/api/measurements")
def measurements(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return [m_out(x) for x in db.scalars(select(Measurement).where(Measurement.user_id==user.id).order_by(Measurement.measured_at.desc())).all()]
@app.post("/api/measurements",status_code=201)
def add_measurement(data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    keys=("weight_kg","waist_cm","chest_cm","hip_cm","arm_cm","thigh_cm")
    try: vals={k:float(data[k]) for k in keys if data.get(k) not in (None,"")}
    except (ValueError,TypeError): raise HTTPException(400,"Ungültiger Messwert.")
    if not vals or any(v<=0 or v>500 for v in vals.values()): raise HTTPException(400,"Bitte gültige Messwerte angeben.")
    try: dt=datetime.fromisoformat(data["measured_at"]) if data.get("measured_at") else datetime.now(timezone.utc)
    except ValueError: raise HTTPException(400,"Ungültiger Zeitpunkt.")
    row=Measurement(user_id=user.id,measured_at=dt,**vals); db.add(row); db.commit(); db.refresh(row); return m_out(row)
@app.delete("/api/measurements/{entry_id}",status_code=204)
def delete_measurement(entry_id:int,db:Session=Depends(get_db),user:User=Depends(current_user)):
    row=db.scalar(select(Measurement).where(Measurement.id==entry_id,Measurement.user_id==user.id))
    if not row: raise HTTPException(404,"Eintrag nicht gefunden.")
    db.delete(row); db.commit(); return Response(status_code=204)
@app.get("/api/food")
def food(db:Session=Depends(get_db),user:User=Depends(current_user)):
    return [f_out(x) for x in db.scalars(select(FoodEntry).where(FoodEntry.user_id==user.id).order_by(FoodEntry.consumed_at.desc()).limit(100)).all()]
@app.post("/api/food",status_code=201)
def add_food(data:dict,db:Session=Depends(get_db),user:User=Depends(current_user)):
    name=str(data.get("food_name","")).strip()
    if not name or len(name)>160: raise HTTPException(400,"Lebensmittelname fehlt.")
    try:
        keys=("amount_g","calories","protein_g","carbs_g","fat_g"); vals={k:float(data.get(k) or 0) for k in keys}
        dt=datetime.fromisoformat(data["consumed_at"]) if data.get("consumed_at") else datetime.now(timezone.utc)
    except (ValueError,TypeError): raise HTTPException(400,"Ungültige Nährwerte oder Zeit.")
    if any(v<0 or v>100000 for v in vals.values()): raise HTTPException(400,"Nährwerte müssen positiv sein.")
    row=FoodEntry(user_id=user.id,food_name=name,meal_type=str(data.get("meal_type","other"))[:20],consumed_at=dt,**vals)
    db.add(row); db.commit(); db.refresh(row); return f_out(row)
@app.get("/api/dashboard")
def dashboard(db:Session=Depends(get_db),user:User=Depends(current_user)):
    today=datetime.now().date()
    entries=db.scalars(select(FoodEntry).where(FoodEntry.user_id==user.id,func.date(FoodEntry.consumed_at)==today)).all()
    latest=db.scalar(select(Measurement).where(Measurement.user_id==user.id).order_by(Measurement.measured_at.desc()))
    return {"username":user.username,"today":{k:sum(getattr(x,k) for x in entries) for k in ("calories","protein_g","carbs_g","fat_g")},"latest_measurement":m_out(latest) if latest else None}
