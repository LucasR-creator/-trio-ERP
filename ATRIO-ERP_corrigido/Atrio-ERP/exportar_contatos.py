"""Ferramenta do OPERADOR DO SERVIDOR para exportar leads locais, sem expor endpoint público."""
import csv
from pathlib import Path
from main import SessionLocal,Inquiry
from sqlalchemy import select
out=Path(__file__).parent/'contatos_recebidos.csv'
with SessionLocal() as db, out.open('w',encoding='utf-8-sig',newline='') as f:
    writer=csv.writer(f,delimiter=';');writer.writerow(['data','nome','email','mensagem'])
    for c in db.scalars(select(Inquiry).order_by(Inquiry.created_at.desc())):
        writer.writerow([c.created_at.isoformat(),c.name,c.email,c.message])
print(f'Exportação criada: {out}')
