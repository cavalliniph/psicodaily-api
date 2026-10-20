-- S3: codigo de e-mail com validade e limite de tentativas. S4: token emitido antes da troca de senha deixa de valer.
-- Nulos nas linhas antigas: CODIGO_EXPIRA_EM nulo = sem validade (ativacao), tentativas nulas = 0, senha nunca trocada.
ALTER TABLE USUARIO ADD CODIGO_EXPIRA_EM TIMESTAMP;
ALTER TABLE USUARIO ADD CODIGO_TENTATIVAS SMALLINT;
ALTER TABLE USUARIO ADD SENHA_ALTERADA_EM TIMESTAMP;
