import os
import sys
import shutil
import glob
import sqlite3
import subprocess
import re
import json

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

def kill_target_processes():
    print("\n🔍 Buscando procesos de Python activos (Streamlit, run_autonomous, etc.)...")
    try:
        # Ejecutar Get-CimInstance en PowerShell para obtener PIDs y CommandLine en formato JSON
        cmd = "powershell -Command \"Get-CimInstance Win32_Process -Filter 'Name = ''python.exe'' or Name = ''pythonw.exe''' | Select-Object ProcessId, CommandLine | ConvertTo-Json\""
        output = subprocess.check_output(cmd, shell=True, text=True, errors='replace').strip()
        if not output:
            print("ℹ️ No se detectaron procesos activos de Python.")
            return
            
        # Parsear JSON (puede ser una lista o un único objeto)
        try:
            data = json.loads(output)
        except Exception:
            # En caso de JSON inválido o vacío
            return
            
        if isinstance(data, dict):
            processes = [data]
        elif isinstance(data, list):
            processes = data
        else:
            processes = []
            
        current_pid = os.getpid()
        for p in processes:
            pid = p.get("ProcessId")
            cmdline = p.get("CommandLine") or ""
            if not pid or pid == current_pid:
                continue
                
            is_target = False
            cmd_lower = cmdline.lower()
            if "streamlit" in cmd_lower:
                print(f"🛑 Detectada instancia de Streamlit (PID {pid}): {cmdline}")
                is_target = True
            elif "run_autonomous.py" in cmd_lower:
                print(f"🛑 Detectado bucle autónomo (PID {pid}): {cmdline}")
                is_target = True
            elif "run_agent.py" in cmd_lower:
                print(f"🛑 Detectado sub-agente (PID {pid}): {cmdline}")
                is_target = True
            elif "interactive_menu.py" in cmd_lower:
                print(f"🛑 Detectado menú interactivo (PID {pid}): {cmdline}")
                is_target = True
                
            if is_target:
                try:
                    print(f"💥 Terminando proceso {pid}...")
                    subprocess.run(f"taskkill /F /PID {pid}", shell=True, check=True)
                except Exception as e:
                    print(f"⚠️ No se pudo terminar el proceso {pid}: {e}")
    except Exception as e:
        print(f"⚠️ Error general al buscar procesos: {e}")

def kill_streamlit_ports():
    print("\n🔍 Buscando procesos escuchando en el puerto 8501...")
    try:
        output = subprocess.check_output(
            'netstat -aon | findstr :8501',
            shell=True,
            text=True,
            errors='replace'
        )
        lines = output.strip().split('\n')
        for line in lines:
            line = line.strip()
            if not line:
                continue
            parts = re.split(r'\s+', line)
            if len(parts) >= 5:
                pid_str = parts[-1]
                try:
                    pid = int(pid_str)
                    if pid > 0 and pid != os.getpid():
                        print(f"🛑 Terminando proceso en puerto 8501 (PID {pid})...")
                        subprocess.run(f"taskkill /F /PID {pid}", shell=True, check=True)
                except ValueError:
                    pass
    except Exception:
        # Es común que no devuelva nada si no hay procesos escuchando
        pass

def clean_database():
    db_path = "data/drugagent.db"
    print(f"\n📁 Limpiando base de datos SQLite en '{db_path}'...")
    if not os.path.exists(db_path):
        print("⚠️ Base de datos no encontrada.")
        return
        
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Eliminar registros de candidatos y corridas
        cursor.execute("DELETE FROM Candidate;")
        cursor.execute("DELETE FROM Run;")
        cursor.execute("DELETE FROM Skill;")
        
        # Resetear contadores de autoincremento si los hay de manera segura
        try:
            cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('Candidate', 'Run', 'Skill');")
        except sqlite3.OperationalError:
            # La tabla sqlite_sequence no existe, ignorar
            pass
        
        conn.commit()
        print("✅ Registros de candidatos, corridas y skills eliminados con éxito.")
    except Exception as e:
        print(f"❌ Error al limpiar base de datos: {e}")
    finally:
        if 'conn' in locals():
            conn.close()

def clean_poses():
    print("\n📁 Limpiando poses guardadas en 'data/docked_poses/'...")
    files = glob.glob("data/docked_poses/*.pdbqt")
    count = 0
    for f in files:
        try:
            os.remove(f)
            count += 1
        except Exception as e:
            print(f"⚠️ No se pudo eliminar '{f}': {e}")
    print(f"✅ Se eliminaron {count} archivos de pose .pdbqt.")

def clean_temp_directories():
    temp_dirs = ["data/dock_tmp", "data/temp_docking"]
    for d in temp_dirs:
        print(f"\n📁 Limpiando directorio temporal '{d}'...")
        try:
            if os.path.exists(d):
                shutil.rmtree(d)
            os.makedirs(d, exist_ok=True)
            print(f"✅ Directorio '{d}' vaciado y recreado con éxito.")
        except Exception as e:
            print(f"⚠️ No se pudo vaciar o recrear '{d}': {e}")

def clean_chroma():
    chroma_dir = "data/chroma"
    print(f"\n📁 Reiniciando base de datos RAG en '{chroma_dir}'...")
    try:
        if os.path.exists(chroma_dir):
            shutil.rmtree(chroma_dir)
        os.makedirs(chroma_dir, exist_ok=True)
        print("✅ Directorio de Chroma RAG reiniciado con éxito.")
    except Exception as e:
        print(f"⚠️ No se pudo reiniciar Chroma: {e}")

def clean_outputs():
    print("\n📁 Limpiando reportes y archivos de salida...")
    outputs = [
        "output/results.json",
        "output/DrugAgent_Report.pdf",
        "output/agent.log"
    ]
    for o in outputs:
        if os.path.exists(o):
            try:
                os.remove(o)
                print(f"✅ Eliminado '{o}'.")
            except Exception as e:
                print(f"⚠️ No se pudo eliminar '{o}': {e}")

if __name__ == "__main__":
    print("🧪 ==================================================== 🧪")
    print("🧪       SISTEMA DE SANEAMIENTO Y REINICIO DE DRUGAGENT     🧪")
    print("🧪 ==================================================== 🧪")
    
    # 1. Matar procesos
    kill_target_processes()
    kill_streamlit_ports()
    
    # 2. Limpiar base de datos
    clean_database()
    
    # 3. Limpiar poses
    clean_poses()
    
    # 4. Limpiar directorios temporales
    clean_temp_directories()
    
    # 5. Reiniciar Chroma RAG
    clean_chroma()
    
    # 6. Eliminar reportes dinámicos
    clean_outputs()
    
    print("\n🎉 ==================================================== 🎉")
    print("🎉      ¡ENTORNO DE DRUGAGENT REINICIADO EXITOSAMENTE!      🎉")
    print("🎉 ==================================================== 🎉\n")
