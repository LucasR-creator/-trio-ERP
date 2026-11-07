"""Átrio ERP — núcleo web. Use HTTPS, PostgreSQL e validação de segurança antes de produção."""
from __future__ import annotations
import csv, hashlib, io, logging, os, secrets, smtplib, time
from email.message import EmailMessage
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import FastAPI, HTTPException, Request, Response, Depends
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import (create_engine, ForeignKey, String, Integer, DateTime, Boolean, Text, UniqueConstraint,
                        select, func, desc, and_)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, Session, sessionmaker

ROOT = Path(__file__).resolve().parent
DB_URL = os.getenv('DATABASE_URL', 'sqlite:///' + str(ROOT / 'data' / 'atrio.db'))
if DB_URL.startswith('sqlite:'):
    (ROOT / 'data').mkdir(parents=True, exist_ok=True)
engine = create_engine(DB_URL, connect_args={'check_same_thread': False} if DB_URL.startswith('sqlite:') else {}, pool_pre_ping=True)
SessionLocal = sessionmaker(engine, expire_on_commit=False)
ph = PasswordHasher(time_cost=3, memory_cost=65536, parallelism=2)

class Base(DeclarativeBase): pass
class Company(Base):
    __tablename__='companies'
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(120))
    tax_id: Mapped[str]=mapped_column(String(32), default='')
    industry: Mapped[str]=mapped_column(String(60), default='Comércio')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True), default=lambda:datetime.now(timezone.utc))
class User(Base):
    __tablename__='users'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    name: Mapped[str]=mapped_column(String(100))
    email: Mapped[str]=mapped_column(String(250),unique=True,index=True)
    password_hash: Mapped[str]=mapped_column(String(255))
    role: Mapped[str]=mapped_column(String(20), default='owner')
    active: Mapped[bool]=mapped_column(Boolean, default=True)
class WebSession(Base):
    __tablename__='sessions'
    id: Mapped[int]=mapped_column(primary_key=True)
    user_id: Mapped[int]=mapped_column(ForeignKey('users.id'),index=True)
    token_hash: Mapped[str]=mapped_column(String(64), unique=True, index=True)
    expires_at: Mapped[datetime]=mapped_column(DateTime(timezone=True))
class Branch(Base):
    __tablename__='branches'
    __table_args__=(UniqueConstraint('company_id','name'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    name: Mapped[str]=mapped_column(String(100))
    city: Mapped[str]=mapped_column(String(100),default='')
class Product(Base):
    __tablename__='products'
    __table_args__=(UniqueConstraint('company_id','sku'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    name: Mapped[str]=mapped_column(String(160))
    sku: Mapped[str]=mapped_column(String(60))
    category: Mapped[str]=mapped_column(String(80),default='Geral')
    brand: Mapped[str]=mapped_column(String(80),default='')
    barcode: Mapped[str]=mapped_column(String(80),default='')
    cost_cents: Mapped[int]=mapped_column(Integer,default=0)
    price_cents: Mapped[int]=mapped_column(Integer,default=0)
    minimum: Mapped[int]=mapped_column(Integer,default=0)
    active: Mapped[bool]=mapped_column(Boolean,default=True)
class Stock(Base):
    __tablename__='stocks'
    __table_args__=(UniqueConstraint('product_id','branch_id'),)
    id: Mapped[int]=mapped_column(primary_key=True)
    product_id: Mapped[int]=mapped_column(ForeignKey('products.id'),index=True)
    branch_id: Mapped[int]=mapped_column(ForeignKey('branches.id'),index=True)
    quantity: Mapped[int]=mapped_column(Integer,default=0)
class StockMove(Base):
    __tablename__='stock_moves'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    branch_id: Mapped[int]=mapped_column(Integer)
    product_id: Mapped[int]=mapped_column(Integer)
    delta: Mapped[int]=mapped_column(Integer)
    reason: Mapped[str]=mapped_column(String(30))
    note: Mapped[str]=mapped_column(String(255), default='')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Customer(Base):
    __tablename__='customers'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    name: Mapped[str]=mapped_column(String(160))
    tax_id: Mapped[str]=mapped_column(String(32),default='')
    email: Mapped[str]=mapped_column(String(250),default='')
    phone: Mapped[str]=mapped_column(String(40),default='')
    kind: Mapped[str]=mapped_column(String(20),default='Pessoa física')
    status: Mapped[str]=mapped_column(String(20),default='Ativo')
class Supplier(Base):
    __tablename__='suppliers'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    name: Mapped[str]=mapped_column(String(160))
    tax_id: Mapped[str]=mapped_column(String(32),default='')
    email: Mapped[str]=mapped_column(String(250),default='')
    phone: Mapped[str]=mapped_column(String(40),default='')
    category: Mapped[str]=mapped_column(String(80),default='Geral')
class Sale(Base):
    __tablename__='sales'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    branch_id: Mapped[int]=mapped_column(Integer)
    customer_id: Mapped[int|None]=mapped_column(Integer,nullable=True)
    payment: Mapped[str]=mapped_column(String(50))
    total_cents: Mapped[int]=mapped_column(Integer)
    cost_cents: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(30),default='Concluída')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class SaleItem(Base):
    __tablename__='sale_items'
    id: Mapped[int]=mapped_column(primary_key=True)
    sale_id: Mapped[int]=mapped_column(ForeignKey('sales.id'),index=True)
    product_id: Mapped[int]=mapped_column(Integer)
    title: Mapped[str]=mapped_column(String(160))
    quantity: Mapped[int]=mapped_column(Integer)
    price_cents: Mapped[int]=mapped_column(Integer)
    cost_cents: Mapped[int]=mapped_column(Integer)
class FinanceEntry(Base):
    __tablename__='finance_entries'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    branch_id: Mapped[int]=mapped_column(Integer)
    direction: Mapped[str]=mapped_column(String(12))
    description: Mapped[str]=mapped_column(String(180))
    category: Mapped[str]=mapped_column(String(80),default='Geral')
    amount_cents: Mapped[int]=mapped_column(Integer)
    status: Mapped[str]=mapped_column(String(20),default='Pago')
    due_date: Mapped[str]=mapped_column(String(10),default='')
    origin: Mapped[str]=mapped_column(String(20),default='manual')
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Activity(Base):
    __tablename__='activities'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    user_id: Mapped[int]=mapped_column(Integer)
    action: Mapped[str]=mapped_column(String(90))
    detail: Mapped[str]=mapped_column(String(255))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Record(Base):
    __tablename__='records'
    id: Mapped[int]=mapped_column(primary_key=True)
    company_id: Mapped[int]=mapped_column(ForeignKey('companies.id'),index=True)
    kind: Mapped[str]=mapped_column(String(40),index=True)
    payload: Mapped[str]=mapped_column(Text)
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))
class Inquiry(Base):
    __tablename__='inquiries'
    id: Mapped[int]=mapped_column(primary_key=True)
    name: Mapped[str]=mapped_column(String(100))
    email: Mapped[str]=mapped_column(String(250))
    message: Mapped[str]=mapped_column(String(2000))
    created_at: Mapped[datetime]=mapped_column(DateTime(timezone=True),default=lambda:datetime.now(timezone.utc))

Base.metadata.create_all(engine)
app=FastAPI(title='Átrio ERP', docs_url=None if os.getenv('APP_ENV')=='production' else '/docs', redoc_url=None)
app.mount('/assets', StaticFiles(directory=ROOT/'static'/'assets'), name='assets')

@app.middleware('http')
async def security_headers(request: Request, call_next):
    if request.method in {'POST','PUT','PATCH','DELETE'} and request.url.path.startswith('/api/'):
        # JSON requests and a non-simple header prevent cross-origin HTML forms from mutating state.
        if request.headers.get('x-atrio-request')!='1':
            return Response('Cabeçalho de segurança obrigatório',status_code=403)
        origin=request.headers.get('origin')
        if origin:
            u=urlsplit(origin)
            if u.netloc!=request.url.netloc:
                return Response('Origem não autorizada',status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='strict-origin-when-cross-origin'
    response.headers['Permissions-Policy']='camera=(), microphone=(), geolocation=()'
    response.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline' https://fonts.googleapis.com; font-src 'self' https://fonts.gstatic.com; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; object-src 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control']='no-store'
    return response

@app.get('/')
def site():return FileResponse(ROOT/'static'/'index.html')
@app.get('/entrar')
def signin():return FileResponse(ROOT/'static'/'entrar.html')
@app.get('/cadastrar')
def signup():return FileResponse(ROOT/'static'/'cadastrar.html')
@app.get('/painel')
def panel():return FileResponse(ROOT/'static'/'painel.html')
@app.get('/privacidade')
def privacy():return FileResponse(ROOT/'static'/'privacidade.html')

class RegisterIn(BaseModel):
    company: str=Field(min_length=2,max_length=120)
    name: str=Field(min_length=2,max_length=100)
    email: EmailStr
    password: str=Field(min_length=12,max_length=128)
class LoginIn(BaseModel):
    email: EmailStr
    password: str
class ContactIn(BaseModel):
    name:str=Field(min_length=2,max_length=100)
    email:EmailStr
    message:str=Field(min_length=5,max_length=2000)
    website:str=''

def db_session():
    with SessionLocal() as db: yield db

def current(request:Request,db:Session=Depends(db_session)):
    token=request.cookies.get('atrio_session','')
    if not token: raise HTTPException(401,'Faça login para continuar.')
    sess=db.scalar(select(WebSession).where(WebSession.token_hash==hashlib.sha256(token.encode()).hexdigest()))
    if not sess or sess.expires_at.replace(tzinfo=timezone.utc)<datetime.now(timezone.utc):
        raise HTTPException(401,'Sua sessão expirou.')
    user=db.get(User,sess.user_id)
    if not user or not user.active: raise HTTPException(401,'Acesso indisponível.')
    return user

def admin(user:User):
    if user.role not in ('owner','admin'):
        raise HTTPException(403,'Permissão insuficiente.')

def stamp(dt:datetime|None):return dt.isoformat() if dt else ''
def money_cents(value:Any):
    try:
        amount=Decimal(str(value)).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)
        if amount<0 or amount>Decimal('999999999.99'):raise ValueError()
        return int(amount*100)
    except (InvalidOperation,ValueError,TypeError):raise HTTPException(422,'Valor monetário inválido.')
def log(db:Session,user:User,action:str,detail:str):
    db.add(Activity(company_id=user.company_id,user_id=user.id,action=action,detail=detail[:255]))
def own_branch(db, company_id, branch_id):
    b=db.scalar(select(Branch).where(Branch.id==branch_id,Branch.company_id==company_id))
    if not b:raise HTTPException(404,'Filial não encontrada.')
    return b

def set_cookie(response,db,user):
    token=secrets.token_urlsafe(48)
    db.add(WebSession(user_id=user.id,token_hash=hashlib.sha256(token.encode()).hexdigest(),expires_at=datetime.now(timezone.utc)+timedelta(days=7)))
    db.commit()
    response.set_cookie('atrio_session',token,max_age=7*86400,httponly=True,secure=os.getenv('APP_ENV')=='production',samesite='strict',path='/')

@app.post('/api/auth/register')
def register(payload:RegisterIn,response:Response,db:Session=Depends(db_session)):
    email=str(payload.email).lower().strip()
    if db.scalar(select(User.id).where(User.email==email)):
        raise HTTPException(409,'Este e-mail já está cadastrado.')
    company=Company(name=payload.company.strip())
    db.add(company);db.flush()
    user=User(company_id=company.id,name=payload.name.strip(),email=email,password_hash=ph.hash(payload.password),role='owner')
    db.add(user);db.flush()
    db.add(Branch(company_id=company.id,name='Matriz',city=''))
    log(db,user,'Conta criada','Cadastro inicial da empresa')
    set_cookie(response,db,user)
    return {'ok':True}

@app.post('/api/auth/login')
def login(payload:LoginIn,response:Response,db:Session=Depends(db_session)):
    # Response indistinguishable for unknown email or wrong password.
    user=db.scalar(select(User).where(User.email==str(payload.email).lower().strip()))
    valid=False
    if user and user.active:
        try:valid=ph.verify(user.password_hash,payload.password)
        except (VerifyMismatchError,VerificationError):pass
    if not valid:raise HTTPException(401,'E-mail ou senha inválidos.')
    set_cookie(response,db,user)
    return {'ok':True}

@app.post('/api/auth/logout')
def logout(request:Request,response:Response,db:Session=Depends(db_session)):
    token=request.cookies.get('atrio_session')
    if token:
        sess=db.scalar(select(WebSession).where(WebSession.token_hash==hashlib.sha256(token.encode()).hexdigest()))
        if sess:db.delete(sess);db.commit()
    response.delete_cookie('atrio_session',path='/')
    return {'ok':True}

@app.get('/api/me')
def me(user:User=Depends(current),db:Session=Depends(db_session)):
    co=db.get(Company,user.company_id)
    branches=db.scalars(select(Branch).where(Branch.company_id==user.company_id).order_by(Branch.id)).all()
    return {'user':{'id':user.id,'name':user.name,'email':user.email,'role':user.role},
            'company':{'id':co.id,'name':co.name,'tax_id':co.tax_id,'industry':co.industry},
            'branches':[{'id':b.id,'name':b.name,'city':b.city} for b in branches]}

@app.put('/api/company')
def edit_company(data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    admin(user);co=db.get(Company,user.company_id)
    for key,max_len in [('name',120),('tax_id',32),('industry',60)]:
        if key in data:
            val=str(data[key]).strip()[:max_len]
            if key=='name' and len(val)<2:raise HTTPException(422,'Nome inválido')
            setattr(co,key,val)
    log(db,user,'Empresa atualizada','Dados cadastrais alterados');db.commit()
    return {'ok':True}

@app.get('/api/branches')
def branches(user:User=Depends(current),db:Session=Depends(db_session)):
    return [{'id':x.id,'name':x.name,'city':x.city} for x in db.scalars(select(Branch).where(Branch.company_id==user.company_id).order_by(Branch.id))]
@app.post('/api/branches')
def create_branch(data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    admin(user);name=str(data.get('name','')).strip()[:100]
    if len(name)<2:raise HTTPException(422,'Informe o nome da filial.')
    if db.scalar(select(Branch.id).where(Branch.company_id==user.company_id,Branch.name==name)):
        raise HTTPException(409,'Já existe uma filial com esse nome.')
    b=Branch(company_id=user.company_id,name=name,city=str(data.get('city',''))[:100]);db.add(b)
    log(db,user,'Filial criada',name);db.commit();return {'id':b.id}

def product_out(p,stocks):
    return {'id':p.id,'name':p.name,'sku':p.sku,'category':p.category,'brand':p.brand,'barcode':p.barcode,
            'cost':p.cost_cents/100,'price':p.price_cents/100,'minimum':p.minimum,'active':p.active,'stocks':stocks,
            'quantity':sum(s['quantity'] for s in stocks)}
@app.get('/api/products')
def get_products(user:User=Depends(current),db:Session=Depends(db_session)):
    products=db.scalars(select(Product).where(Product.company_id==user.company_id).order_by(Product.name)).all()
    ids=[p.id for p in products];stocks=defaultdict(list)
    if ids:
        for s in db.scalars(select(Stock).where(Stock.product_id.in_(ids))):
            stocks[s.product_id].append({'branch_id':s.branch_id,'quantity':s.quantity})
    return [product_out(p,stocks[p.id]) for p in products]
@app.post('/api/products')
def add_product(data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    name=str(data.get('name','')).strip()[:160];sku=str(data.get('sku','')).strip().upper()[:60]
    if len(name)<2 or not sku:raise HTTPException(422,'Nome e SKU são obrigatórios.')
    if db.scalar(select(Product.id).where(Product.company_id==user.company_id,Product.sku==sku)):
        raise HTTPException(409,'Este SKU já existe.')
    minimum=int(data.get('minimum',0))
    if minimum<0:raise HTTPException(422,'Mínimo inválido')
    p=Product(company_id=user.company_id,name=name,sku=sku,category=str(data.get('category','Geral'))[:80],
        brand=str(data.get('brand',''))[:80],barcode=str(data.get('barcode',''))[:80],
        cost_cents=money_cents(data.get('cost',0)),price_cents=money_cents(data.get('price',0)),minimum=minimum)
    # Estoque inicial opcional, vinculado à filial selecionada.
    try:
        initial=int(data.get('initial_quantity',0) or 0)
    except (ValueError,TypeError):
        raise HTTPException(422,'Estoque inicial deve ser um número inteiro.')
    if initial<0 or initial>1000000:
        raise HTTPException(422,'Estoque inicial deve estar entre 0 e 1.000.000.')
    branch_id=data.get('branch_id')
    if initial:
        if not branch_id:raise HTTPException(422,'Selecione uma unidade para o estoque inicial.')
        own_branch(db,user.company_id,int(branch_id))
    db.add(p);db.flush()
    if initial:
        db.add(Stock(product_id=p.id,branch_id=int(branch_id),quantity=initial))
        db.add(StockMove(company_id=user.company_id,branch_id=int(branch_id),product_id=p.id,
            delta=initial,reason='Estoque inicial',note='Saldo informado no cadastro do produto'))
    log(db,user,'Produto cadastrado',f'{sku} · {name}');db.commit();return {'id':p.id}
@app.put('/api/products/{pid}')
def update_product(pid:int,data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    p=db.scalar(select(Product).where(Product.id==pid,Product.company_id==user.company_id))
    if not p:raise HTTPException(404,'Produto não encontrado.')
    for key,n in [('name',160),('category',80),('brand',80),('barcode',80)]:
        if key in data:setattr(p,key,str(data[key]).strip()[:n])
    for key in ('cost','price'):
        if key in data:setattr(p,key+'_cents',money_cents(data[key]))
    if 'minimum' in data:p.minimum=max(0,int(data['minimum']))
    if 'active' in data:p.active=bool(data['active'])
    log(db,user,'Produto atualizado',p.sku);db.commit();return {'ok':True}
@app.post('/api/stock')
def move_stock(data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    pid=int(data.get('product_id',0));bid=int(data.get('branch_id',0));delta=int(data.get('delta',0))
    if delta==0 or abs(delta)>1000000:raise HTTPException(422,'Quantidade inválida.')
    p=db.scalar(select(Product).where(Product.id==pid,Product.company_id==user.company_id,Product.active==True))
    if not p:raise HTTPException(404,'Produto não encontrado')
    own_branch(db,user.company_id,bid)
    s=db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==bid).with_for_update())
    if not s:s=Stock(product_id=pid,branch_id=bid,quantity=0);db.add(s)
    if s.quantity+delta<0:raise HTTPException(409,'Saldo insuficiente para esta saída.')
    s.quantity+=delta
    db.add(StockMove(company_id=user.company_id,branch_id=bid,product_id=pid,delta=delta,
        reason='Ajuste manual',note=str(data.get('note',''))[:255]))
    log(db,user,'Estoque movimentado',f'{p.sku} · {delta:+d} unidades')
    db.commit();return {'quantity':s.quantity}

class BasicContact(BaseModel):
    name:str=Field(min_length=2,max_length=160)
    tax_id:str=Field(default='',max_length=32)
    email:str=Field(default='',max_length=250)
    phone:str=Field(default='',max_length=40)
    kind:str=Field(default='Pessoa física',max_length=30)
    category:str=Field(default='Geral',max_length=80)
@app.get('/api/contacts/{typ}')
def list_contacts(typ:str,user:User=Depends(current),db:Session=Depends(db_session)):
    if typ not in ('customers','suppliers'):raise HTTPException(404)
    cls=Customer if typ=='customers' else Supplier
    rows=db.scalars(select(cls).where(cls.company_id==user.company_id).order_by(cls.name)).all()
    return [{'id':x.id,'name':x.name,'tax_id':x.tax_id,'email':x.email,'phone':x.phone,
             'kind':getattr(x,'kind',''),'category':getattr(x,'category',''),'status':getattr(x,'status','Ativo')} for x in rows]
@app.post('/api/contacts/{typ}')
def add_contact(typ:str,data:BasicContact,user:User=Depends(current),db:Session=Depends(db_session)):
    if typ not in ('customers','suppliers'):raise HTTPException(404)
    if typ=='customers':obj=Customer(company_id=user.company_id,name=data.name.strip(),tax_id=data.tax_id,email=data.email,phone=data.phone,kind=data.kind)
    else:obj=Supplier(company_id=user.company_id,name=data.name.strip(),tax_id=data.tax_id,email=data.email,phone=data.phone,category=data.category)
    db.add(obj);db.flush();log(db,user,'Cadastro criado',data.name);db.commit();return {'id':obj.id}
@app.put('/api/contacts/{typ}/{rid}')
def edit_contact(typ:str,rid:int,data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    if typ not in ('customers','suppliers'):raise HTTPException(404)
    cls=Customer if typ=='customers' else Supplier
    obj=db.scalar(select(cls).where(cls.id==rid,cls.company_id==user.company_id))
    if not obj:raise HTTPException(404)
    for key,cap in [('name',160),('tax_id',32),('email',250),('phone',40),('kind',20),('category',80),('status',20)]:
        if key in data and hasattr(obj,key):setattr(obj,key,str(data[key])[:cap])
    log(db,user,'Cadastro atualizado',obj.name);db.commit();return {'ok':True}

class SaleRequest(BaseModel):
    branch_id:int
    customer_id:int|None=None
    payment:str=Field(max_length=50)
    items:list[dict]=Field(min_length=1,max_length=100)
@app.get('/api/sales')
def sales(user:User=Depends(current),db:Session=Depends(db_session)):
    rows=db.scalars(select(Sale).where(Sale.company_id==user.company_id).order_by(desc(Sale.id)).limit(300)).all()
    return [{'id':x.id,'branch_id':x.branch_id,'customer_id':x.customer_id,'payment':x.payment,
             'total':x.total_cents/100,'cost':x.cost_cents/100,'status':x.status,'created_at':stamp(x.created_at)} for x in rows]
@app.post('/api/sales')
def create_sale(data:SaleRequest,user:User=Depends(current),db:Session=Depends(db_session)):
    own_branch(db,user.company_id,data.branch_id)
    if data.customer_id and not db.scalar(select(Customer.id).where(Customer.id==data.customer_id,Customer.company_id==user.company_id)):
        raise HTTPException(404,'Cliente não encontrado.')
    if data.payment not in ('Pix','Dinheiro','Cartão','Boleto','Outro'):
        raise HTTPException(422,'Meio de pagamento não aceito.')
    quantities=defaultdict(int)
    for item in data.items:
        try: pid=int(item['product_id']);qty=int(item['quantity'])
        except (KeyError,ValueError,TypeError):raise HTTPException(422,'Item inválido.')
        if qty<=0 or qty>100000:raise HTTPException(422,'Quantidade inválida.')
        quantities[pid]+=qty
    prices=[];total=cost=0
    for pid,qty in sorted(quantities.items()):
        p=db.scalar(select(Product).where(Product.id==pid,Product.company_id==user.company_id,Product.active==True))
        if not p:raise HTTPException(404,f'Produto {pid} indisponível.')
        s=db.scalar(select(Stock).where(Stock.product_id==pid,Stock.branch_id==data.branch_id).with_for_update())
        if not s or s.quantity<qty:raise HTTPException(409,f'Estoque insuficiente: {p.name}.')
        s.quantity-=qty;prices.append((p,qty));total+=p.price_cents*qty;cost+=p.cost_cents*qty
    sale=Sale(company_id=user.company_id,branch_id=data.branch_id,customer_id=data.customer_id,
              payment=data.payment,total_cents=total,cost_cents=cost)
    db.add(sale);db.flush()
    for p,qty in prices:
        db.add(SaleItem(sale_id=sale.id,product_id=p.id,title=p.name,quantity=qty,price_cents=p.price_cents,cost_cents=p.cost_cents))
        db.add(StockMove(company_id=user.company_id,branch_id=data.branch_id,product_id=p.id,
            delta=-qty,reason='Venda',note=f'Pedido #{sale.id}'))
    status='Pendente' if data.payment=='Boleto' else 'Pago'
    db.add(FinanceEntry(company_id=user.company_id,branch_id=data.branch_id,direction='entrada',
        description=f'Venda #{sale.id}',category='Vendas',amount_cents=total,status=status,origin='venda'))
    log(db,user,'Venda registrada',f'Pedido #{sale.id} · R$ {total/100:.2f}')
    db.commit();return {'id':sale.id,'total':total/100}

@app.get('/api/finance')
def finance(user:User=Depends(current),db:Session=Depends(db_session)):
    rows=db.scalars(select(FinanceEntry).where(FinanceEntry.company_id==user.company_id).order_by(desc(FinanceEntry.id)).limit(500)).all()
    return [{'id':x.id,'branch_id':x.branch_id,'direction':x.direction,'description':x.description,'category':x.category,
             'amount':x.amount_cents/100,'status':x.status,'due_date':x.due_date,'origin':x.origin,'created_at':stamp(x.created_at)} for x in rows]
@app.post('/api/finance')
def add_finance(data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    direction=str(data.get('direction',''))
    if direction not in ('entrada','saida'):raise HTTPException(422,'Tipo inválido')
    status=str(data.get('status','Pago'))
    if status not in ('Pago','Pendente'):raise HTTPException(422,'Situação inválida')
    amount=money_cents(data.get('amount',0));description=str(data.get('description','')).strip()[:180]
    if amount<=0 or len(description)<2:raise HTTPException(422,'Descrição e valor são obrigatórios.')
    bid=int(data.get('branch_id',0));own_branch(db,user.company_id,bid)
    entry=FinanceEntry(company_id=user.company_id,branch_id=bid,direction=direction,description=description,
        category=str(data.get('category','Geral'))[:80],amount_cents=amount,status=status,
        due_date=str(data.get('due_date',''))[:10])
    db.add(entry);log(db,user,'Lançamento financeiro',description);db.commit();return {'id':entry.id}
@app.put('/api/finance/{fid}')
def settle(fid:int,user:User=Depends(current),db:Session=Depends(db_session)):
    obj=db.scalar(select(FinanceEntry).where(FinanceEntry.id==fid,FinanceEntry.company_id==user.company_id))
    if not obj:raise HTTPException(404)
    obj.status='Pago';log(db,user,'Pagamento confirmado',obj.description);db.commit();return {'ok':True}

import json
ALLOWED_KINDS={'employees','services','contracts','banks','fiscal','purchases','notifications','support'}
KIND_ALLOWED_FIELDS={
 'employees':{'name','role','department','branch','email','phone','status'},
 'services':{'title','customer','owner','deadline','value','status','notes'},
 'contracts':{'title','party','start','deadline','value','status','notes'},
 'banks':{'name','agency','account','opening_balance','type'},
 'fiscal':{'number','type','issuer','issue_date','value','status','notes'},
 'purchases':{'title','supplier','deadline','value','status','notes'},
 'notifications':{'title','severity','status','notes'},
 'support':{'subject','message','status'}
}
@app.get('/api/records/{kind}')
def records(kind:str,user:User=Depends(current),db:Session=Depends(db_session)):
    if kind not in ALLOWED_KINDS:raise HTTPException(404)
    rows=db.scalars(select(Record).where(Record.company_id==user.company_id,Record.kind==kind).order_by(desc(Record.id)).limit(400)).all()
    return [{'id':r.id,**json.loads(r.payload),'created_at':stamp(r.created_at)} for r in rows]
@app.post('/api/records/{kind}')
def create_record(kind:str,data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    if kind not in ALLOWED_KINDS:raise HTTPException(404)
    if kind=='fiscal':
        # Registry only. No issuance, tax calculation, signature or SEFAZ integration.
        data['status']='Registrada'
    safe={k:str(v).strip()[:450] for k,v in data.items() if k in KIND_ALLOWED_FIELDS[kind] and isinstance(v,(str,int,float))}
    if not safe or not any(v for v in safe.values()):raise HTTPException(422,'Preencha os campos solicitados.')
    rec=Record(company_id=user.company_id,kind=kind,payload=json.dumps(safe,ensure_ascii=False));db.add(rec)
    log(db,user,'Registro criado',f'{kind} · {next(iter(safe.values()))[:90]}');db.commit();return {'id':rec.id}
@app.put('/api/records/{kind}/{rid}')
def edit_record(kind:str,rid:int,data:dict,user:User=Depends(current),db:Session=Depends(db_session)):
    if kind not in ALLOWED_KINDS:raise HTTPException(404)
    rec=db.scalar(select(Record).where(Record.id==rid,Record.company_id==user.company_id,Record.kind==kind))
    if not rec:raise HTTPException(404)
    old=json.loads(rec.payload)
    for k,v in data.items():
        if k in KIND_ALLOWED_FIELDS[kind] and k!='status' or (k=='status' and kind!='fiscal'):
            old[k]=str(v)[:450]
    rec.payload=json.dumps(old,ensure_ascii=False)
    log(db,user,'Registro atualizado',kind+': '+str(rid));db.commit();return {'ok':True}

@app.get('/api/dashboard')
def dashboard(user:User=Depends(current),db:Session=Depends(db_session)):
    cid=user.company_id;now=datetime.now(timezone.utc)
    sales=db.scalars(select(Sale).where(Sale.company_id==cid,Sale.status=='Concluída').order_by(desc(Sale.id))).all()
    entries=db.scalars(select(FinanceEntry).where(FinanceEntry.company_id==cid)).all()
    products=db.scalars(select(Product).where(Product.company_id==cid,Product.active==True)).all()
    pids=[p.id for p in products]
    stocks=defaultdict(int)
    if pids:
        for s in db.scalars(select(Stock).where(Stock.product_id.in_(pids))):stocks[s.product_id]+=s.quantity
    month_sales=[s for s in sales if s.created_at.year==now.year and s.created_at.month==now.month]
    previous_year, previous_month = (now.year-1, 12) if now.month == 1 else (now.year, now.month-1)
    previous_month_sales=[s for s in sales if s.created_at.year==previous_year and s.created_at.month==previous_month]
    previous_month_revenue=sum(s.total_cents for s in previous_month_sales)
    day_sales=[s for s in sales if s.created_at.date()==now.date()]
    year_sales=[s for s in sales if s.created_at.year==now.year]
    month_out=sum(e.amount_cents for e in entries if e.direction=='saida' and e.status=='Pago' and e.created_at.year==now.year and e.created_at.month==now.month)
    month_cogs=sum(s.cost_cents for s in month_sales)
    month_revenue=sum(s.total_cents for s in month_sales)
    cash=sum((1 if e.direction=='entrada' else -1)*e.amount_cents for e in entries if e.status=='Pago')
    chart=defaultdict(int)
    for s in sales: chart[s.created_at.strftime('%Y-%m')]+=s.total_cents
    activity=db.scalars(select(Activity).where(Activity.company_id==cid).order_by(desc(Activity.id)).limit(8)).all()
    low=[{'id':p.id,'name':p.name,'sku':p.sku,'quantity':stocks[p.id],'minimum':p.minimum} for p in products if stocks[p.id]<=p.minimum]
    pending_in=sum(e.amount_cents for e in entries if e.direction=='entrada' and e.status=='Pendente')
    pending_out=sum(e.amount_cents for e in entries if e.direction=='saida' and e.status=='Pendente')
    return {'day_revenue':sum(s.total_cents for s in day_sales)/100,'month_revenue':month_revenue/100,
            'previous_month_revenue':previous_month_revenue/100,
            'monthly_change_percent':round(100*(month_revenue-previous_month_revenue)/previous_month_revenue,1) if previous_month_revenue else None,
            'year_revenue':sum(s.total_cents for s in year_sales)/100,
            'gross_profit':(month_revenue-month_cogs)/100,'operating_result':(month_revenue-month_cogs-month_out)/100,
            'expenses':month_out/100,'cash':cash/100,'sales_count':len(sales),
            'month_sales_count':len(month_sales),'product_count':len(products),'stock_units':sum(stocks.values()),
            'low_stock':low[:12], 'low_stock_count':len(low),
            'customer_count':db.scalar(select(func.count(Customer.id)).where(Customer.company_id==cid)),
            'pending_in':pending_in/100,'pending_out':pending_out/100,
            'monthly_series':[{'month':k,'revenue':chart[k]/100} for k in sorted(chart)[-8:]],
            'activities':[{'action':a.action,'detail':a.detail,'created_at':stamp(a.created_at)} for a in activity]}

@app.get('/api/activities')
def activities(user:User=Depends(current),db:Session=Depends(db_session)):
    return [{'id':a.id,'action':a.action,'detail':a.detail,'created_at':stamp(a.created_at)}
            for a in db.scalars(select(Activity).where(Activity.company_id==user.company_id).order_by(desc(Activity.id)).limit(80))]

@app.post('/api/contact')
def contact(data:ContactIn,db:Session=Depends(db_session)):
    if data.website:return {'ok':True}
    db.add(Inquiry(name=data.name.strip(),email=str(data.email),message=data.message.strip()));db.commit()
    if os.getenv('SMTP_HOST') and os.getenv('CONTACT_NOTIFY_EMAIL'):
        try:
            msg=EmailMessage()
            msg['Subject']='Átrio | Novo contato comercial'
            msg['From']=os.getenv('SMTP_FROM',os.getenv('SMTP_USER','contato@exemplo.invalid'))
            msg['To']=os.getenv('CONTACT_NOTIFY_EMAIL')
            msg['Reply-To']=str(data.email)
            msg.set_content(f'Nome: {data.name}\nE-mail: {data.email}\n\n{data.message}')
            port=int(os.getenv('SMTP_PORT','587'))
            with smtplib.SMTP(os.getenv('SMTP_HOST'),port,timeout=8) as server:
                server.starttls()
                if os.getenv('SMTP_USER'):
                    server.login(os.getenv('SMTP_USER'),os.getenv('SMTP_PASSWORD',''))
                server.send_message(msg)
        except Exception:
            logging.exception('Falha ao enviar notificação de contato; o registro foi preservado.')
    return {'ok':True,'message':'Mensagem recebida e registrada. A equipe responsável poderá consultar seu contato.'}

@app.get('/api/export/{kind}')
def export_csv(kind:str,user:User=Depends(current),db:Session=Depends(db_session)):
    if kind not in ('products','customers','suppliers','sales','finance'):raise HTTPException(404)
    data= {'products':get_products,'customers':lambda **kw:list_contacts('customers',**kw),
           'suppliers':lambda **kw:list_contacts('suppliers',**kw),'sales':sales,'finance':finance}[kind](user=user,db=db)
    if kind=='products':
        for row in data:row.pop('stocks',None)
    columns=list(data[0]) if data else ['Sem registros']
    out=io.StringIO();writer=csv.writer(out,delimiter=';');writer.writerow(columns)
    for row in data:
        def safe(v):
            s=str(v)
            return "'"+s if s and s[0] in '=+-@\t\r' else s
        writer.writerow([safe(row.get(c,'')) for c in columns])
    return Response('\ufeff'+out.getvalue(),media_type='text/csv; charset=utf-8',headers={'Content-Disposition':f'attachment; filename="atrio-{kind}.csv"'})

@app.get('/api/health')
def health():return {'status':'ok'}
