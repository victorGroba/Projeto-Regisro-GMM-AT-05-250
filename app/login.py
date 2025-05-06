from flask import render_template, request, redirect, url_for, flash, session
from . import bp  # Importe o Blueprint corretamente
from .models import Usuario
from .forms import LoginForm

@bp.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()

    if form.validate_on_submit():
        usuario = Usuario.query.filter_by(username=form.username.data).first()

        if usuario and usuario.check_senha(form.senha.data):
            session['usuario_id'] = usuario.id  # Armazena o ID do usuário na sessão
            session['usuario_nome'] = usuario.username  # Armazena o nome do usuário na sessão
            flash('Login bem-sucedido!', 'success')
            return redirect(url_for('main.index'))
        else:
            flash('Nome de usuário ou senha inválidos.', 'danger')

    return render_template('login.html', form=form)
