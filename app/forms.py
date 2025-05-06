from flask_wtf import FlaskForm
from wtforms import StringField, FloatField, TextAreaField, SubmitField, PasswordField, SelectField, BooleanField
from wtforms.validators import DataRequired




class TermometroForm(FlaskForm):
    setor = StringField('Setor', validators=[DataRequired()])
    equipamento = StringField('Equipamento', validators=[DataRequired()])
    especificacao = StringField('Especificação')
    identificacao = StringField('Identificação do Termômetro', validators=[DataRequired()])
    padrao_identificacao = StringField('Identificação do Termômetro Padrão')
    submit = SubmitField('Cadastrar')

class VerificacaoForm(FlaskForm):
    temperatura_atual = FloatField('Temperatura Atual (°C)', validators=[DataRequired()])
    temperatura_max = FloatField('Temperatura Máxima (°C)', validators=[DataRequired()])
    temperatura_min = FloatField('Temperatura Mínima (°C)', validators=[DataRequired()])
    responsavel = StringField('Responsável', validators=[DataRequired()])
    
    observacao = SelectField('Observação (opcional)', choices=[
        ('Nenhuma', 'Nenhuma'),
        ('A', 'A. Descongelamento/Limpeza'),
        ('B', 'B. Verificação Vedação'),
        ('C', 'C. Verificação Validade de Insumos'),
        ('D', 'D. Solicitação Manutenção Corretiva'),
        ('E', 'E. Interrupção Energia Elétrica'),
        ('F', 'F. Religagem do termostato'),
        ('G', 'G. Porta muito tempo aberta'),
        ('H', 'H. Limpeza após contaminação'),
        ('I', 'I. Outro (verificar observações)')
    ])
    
    submit = SubmitField('Registrar Verificação')
    


class LoginForm(FlaskForm):
    username = StringField('Usuário', validators=[DataRequired()])
    senha = PasswordField('Senha', validators=[DataRequired()])
    submit = SubmitField('Entrar')

    

class UsuarioForm(FlaskForm):
    username = StringField('Usuário', validators=[DataRequired()])
    senha = PasswordField('Senha', validators=[DataRequired()])
    is_admin = BooleanField('Administrador')
    submit = SubmitField('Cadastrar')