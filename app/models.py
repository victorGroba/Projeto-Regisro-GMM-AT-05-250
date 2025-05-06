from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import DataRequired
import pytz
from datetime import datetime
from . import db
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    senha_hash = db.Column(db.String(128), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)  # 👈 aqui

    def set_senha(self, senha):
        self.senha_hash = generate_password_hash(senha)

    def check_senha(self, senha):
        return check_password_hash(self.senha_hash, senha)


class Termometro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    setor = db.Column(db.String(100))
    equipamento = db.Column(db.String(100))
    especificacao = db.Column(db.String(100))
    identificacao = db.Column(db.String(50))
    padrao_identificacao = db.Column(db.String(50))
    
    # Define o relacionamento com as verificações
    verificacoes = db.relationship('Verificacao', backref='termometro', lazy=True)

class Verificacao(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)
    temperatura_atual = db.Column(db.Float)
    temperatura_max = db.Column(db.Float)
    temperatura_min = db.Column(db.Float)
    responsavel = db.Column(db.String(100))
    observacao = db.Column(db.String(100))
    termometro_id = db.Column(db.Integer, db.ForeignKey('termometro.id'))

    def get_data_hora_sp(self):
        """Converte data_hora (UTC naive) para horário de São Paulo."""
        # 1) localiza em UTC
        utc = pytz.utc.localize(self.data_hora)
        # 2) converte para SP
        sp_tz = pytz.timezone('America/Sao_Paulo')
        sp_time = utc.astimezone(sp_tz)
        return sp_time

    def __repr__(self):
        return f'<Verificacao {self.id}>'
    
    


