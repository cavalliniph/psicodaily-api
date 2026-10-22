-- 30: lembretes por e-mail e WhatsApp 24h e 1h antes da sessao; a coluna marca o que ja foi avisado.
ALTER TABLE SESSAO ADD LEMBRETE_24H_EM TIMESTAMP;
ALTER TABLE SESSAO ADD LEMBRETE_1H_EM TIMESTAMP;
