-- F0.1, passo 1 de 3: o banco tem DEFAULT CHARACTER SET ISO8859_1, e texto livre com travessao,
-- aspas curvas, emoji ou letras fora do Latin-1 dava 500 ("Cannot transliterate character").
-- ALTER COLUMN ... CHARACTER SET e ignorado pelo Firebird, entao a troca e: coluna nova UTF8,
-- copia (0003), remove a antiga e renomeia a nova para o mesmo nome e posicao (0004).
ALTER TABLE USUARIO ADD EMAIL_UTF8 VARCHAR(255) CHARACTER SET UTF8;
ALTER TABLE USUARIO ADD NOME_UTF8 VARCHAR(150) CHARACTER SET UTF8;
ALTER TABLE PROFISSIONAL ADD FORMACAO_UTF8 VARCHAR(1000) CHARACTER SET UTF8;
ALTER TABLE AVALIACAO ADD COMENTARIO_UTF8 VARCHAR(500) CHARACTER SET UTF8;
