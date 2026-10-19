-- Dados FICTICIOS para dev e CI: python database/migrar.py --criar --seed database/seed.sql
-- Nunca rodar em producao. Os testes de tests/ usam os IDs 22 (psicologo), 23 e 25 (pacientes).
-- Senha de todos: Senha@123. CPFs validos, mas inventados.
-- Restricoes dos testes: nenhum outro profissional com abordagem TCC nem com avaliacao.

INSERT INTO USUARIO (ID_USUARIO, EMAIL, NOME, TELEFONE, CPF, USUARIO_ROLE, SENHA, ATIVO) VALUES
    (22, 'psicologa.teste@exemplo.com', 'Ana Psicologa Teste', '(11) 91111-1111', '10433218100', 'PSICOLOGO',
     '$2b$12$Oz027XjyKjGC2AvSZOPAveDGnzmfkNpja7zVMBdTmTAC.o/EiCUfa', TRUE);
INSERT INTO USUARIO (ID_USUARIO, EMAIL, NOME, TELEFONE, CPF, USUARIO_ROLE, SENHA, ATIVO) VALUES
    (23, 'paciente.teste@exemplo.com', 'Bruno Paciente Teste', '(11) 92222-2222', '96001338914', 'PACIENTE',
     '$2b$12$Oz027XjyKjGC2AvSZOPAveDGnzmfkNpja7zVMBdTmTAC.o/EiCUfa', TRUE);
INSERT INTO USUARIO (ID_USUARIO, EMAIL, NOME, TELEFONE, CPF, USUARIO_ROLE, SENHA, ATIVO) VALUES
    (24, 'psiquiatra.teste@exemplo.com', 'Carla Psiquiatra Teste', '(11) 93333-3333', '08386379499', 'PSIQUIATRA',
     '$2b$12$Oz027XjyKjGC2AvSZOPAveDGnzmfkNpja7zVMBdTmTAC.o/EiCUfa', TRUE);
INSERT INTO USUARIO (ID_USUARIO, EMAIL, NOME, TELEFONE, CPF, USUARIO_ROLE, SENHA, ATIVO) VALUES
    (25, 'outro.paciente@exemplo.com', 'Daniel Paciente Teste', '(11) 94444-4444', '02654235114', 'PACIENTE',
     '$2b$12$Oz027XjyKjGC2AvSZOPAveDGnzmfkNpja7zVMBdTmTAC.o/EiCUfa', TRUE);

INSERT INTO PROFISSIONAL (USUARIO_ID, CONSELHO_TIPO, CONSELHO_NUMERO, ESPECIALIDADE, PRECO_HORA, DESCRICAO) VALUES
    (22, 'CRP', '06/123456', 'Psicologia', 12000, 'Atendimento de adultos com foco em ansiedade.');
INSERT INTO PROFISSIONAL (USUARIO_ID, CONSELHO_TIPO, CONSELHO_NUMERO, ESPECIALIDADE, PRECO_HORA, DESCRICAO,
                          MODALIDADE, IDIOMAS) VALUES
    (24, 'CRM', 'SP/654321', 'Psiquiatria', 30000, 'Psiquiatria clinica e acompanhamento medicamentoso.',
     'ONLINE', 'Português,Inglês');

INSERT INTO REGISTRO (USUARIO_ID, HUMOR, QUALIDADE_SONO, MINUTOS_SONO, EXERCICIO_FISICO, ANOTACAO, CRIADO_EM) VALUES
    (23, 'BOM', 'BOA', 450, TRUE, 'Registro de exemplo.', DATEADD(-2 DAY TO CURRENT_DATE));
INSERT INTO REGISTRO (USUARIO_ID, HUMOR, QUALIDADE_SONO, MINUTOS_SONO, EXERCICIO_FISICO, ANOTACAO, CRIADO_EM) VALUES
    (23, 'NEUTRO', 'REGULAR', 380, FALSE, 'Outro registro de exemplo.', DATEADD(-1 DAY TO CURRENT_DATE));

-- Os proximos IDs gerados nao colidem com os fixos acima
ALTER TABLE USUARIO ALTER ID_USUARIO RESTART WITH 100;
ALTER TABLE PROFISSIONAL ALTER USUARIO_ID RESTART WITH 100;
