"""
Database Connection Manager
Maneja la conexión sincrónica a la base de datos de Prisma SQLite.
"""
from prisma import Prisma

# Instancia global del cliente
db = Prisma()

def init_db():
    """Conecta a la base de datos si no está conectada."""
    if not db.is_connected():
        db.connect()

def close_db():
    """Cierra la conexión a la base de datos."""
    if db.is_connected():
        db.disconnect()
