class ErroNegocio(Exception):
    """Regra violada; o app.py devolve {'error': mensagem, **extra} com o status."""

    def __init__(self, mensagem, status=400, **extra):
        super().__init__(mensagem)
        self.mensagem = mensagem
        self.status = status
        self.extra = extra
