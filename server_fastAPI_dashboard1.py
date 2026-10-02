from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import psycopg2
from pydantic import BaseModel
import os
from fastapi.responses import FileResponse


app = FastAPI()

@app.get("/")
async def serve_dashboard():
    # ดึง Path ของโฟลเดอร์ที่ไฟล์ Python นี้อยู่อัตโนมัติ
    file_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    return FileResponse(file_path)

# อนุญาตให้เชื่อมต่อ API ได้ทุกอุปกรณ์
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_CONFIG = "postgresql://neondb_owner:password@ep-xyz-singapore.aws.neon.tech/neondb?sslmode=require"

# --- Schema ข้อมูล ---
class TelemetryInput(BaseModel):
    device_id: str
    building_id: str
    floor_no: str
    room_no: str
    temperature: float
    setpoint: float
    humidity: float
    condenser_status: bool
    is_online: bool

class DeviceRegisterInput(BaseModel):
    device_id: str
    device_name: str
    location: str
    ip_address: str
    registered_by: str

# 1. API ดึงข้อมูลสถานะปัจจุบัน
@app.get("/api/hvac/telemetry")
def get_current_hvac():
    try:
        with psycopg2.connect(DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT DISTINCT ON (device_id)
                        device_id, building_id, floor_no, room_no,
                        temperature, setpoint, humidity, condenser_status, is_online, created_at
                    FROM hvac_telemetry
                    ORDER BY device_id, created_at DESC;
                """)
                rows = cur.fetchall()
                return [{
                    "device_id": r[0], "building": r[1], "floor": r[2], "room": r[3],
                    "temperature": float(r[4]), "setpoint": float(r[5]), "humidity": float(r[6]),
                    "condenser": r[7], "is_online": r[8],
                    "updated_at": str(r[9]).split(".")[0] if r[9] else ""
                } for r in rows]
    except Exception as e:
        print("Database Error:", e)
        return []
# 2. API รับข้อมูลจาก ESP32 บันทึกลง hvac_telemetry
@app.post("/api/hvac/telemetry")
def create_telemetry(data: TelemetryInput):
    try:
        with psycopg2.connect(DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO hvac_telemetry 
                    (device_id, building_id, floor_no, room_no, temperature, setpoint, humidity, condenser_status, is_online)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    data.device_id,
                    data.building_id,
                    data.floor_no,
                    data.room_no,
                    data.temperature,
                    data.setpoint,
                    data.humidity,
                    1 if data.condenser_status else 0,  # condenser_status เป็น INTEGER (ส่ง 1 หรือ 0)
                    bool(data.is_online)                 # is_online เป็น BOOLEAN (ส่ง True หรือ False)
                ))
                conn.commit()
        return {"status": "success", "message": "Data saved successfully"}
    except Exception as e:
        print("Database Error:", e)
        return {"status": "error", "message": str(e)}

# 3. API บันทึกการลงทะเบียนอุปกรณ์ลงตาราง device ใน PostgreSQL
@app.post("/api/device/register")
def register_device(data: DeviceRegisterInput):
    try:
        with psycopg2.connect(DB_CONFIG) as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO device (device_id, device_name, location, ip_address, registered_by)
                    VALUES (%s, %s, %s, %s, %s)
                    ON CONFLICT (device_id) DO UPDATE 
                    SET device_name = EXCLUDED.device_name,
                        location = EXCLUDED.location,
                        ip_address = EXCLUDED.ip_address,
                        registered_by = EXCLUDED.registered_by
                """, (
                    data.device_id, 
                    data.device_name, 
                    data.location, 
                    data.ip_address, 
                    data.registered_by
                ))
                conn.commit()
        return {"status": "success", "message": "Device registered successfully"}
    except Exception as e:
        print("Database Error:", e)
        return {"status": "error", "message": str(e)}
    

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
