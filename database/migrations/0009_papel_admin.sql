-- F8: papel ADMIN (painel e auditoria) e data de cadastro para as metricas da feature 25.
ALTER DOMAIN DM_ROLE DROP CONSTRAINT;
ALTER DOMAIN DM_ROLE ADD CONSTRAINT CHECK (VALUE IN ('PACIENTE', 'PSICOLOGO', 'PSIQUIATRA', 'ADMIN'));
-- Sem UPDATE de proposito: quem se cadastrou antes fica NULL e nao conta como cadastro novo
ALTER TABLE USUARIO ADD CRIADO_EM TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
