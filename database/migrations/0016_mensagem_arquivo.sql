-- F6/feature 19: arquivo anexado a mensagem do chat, no bucket R2 privado. Sem arquivo, as quatro ficam nulas.
-- ARQUIVO_CHAVE e o caminho no bucket; o nome original so serve para exibir e para o download.
ALTER TABLE MENSAGEM ADD ARQUIVO_CHAVE VARCHAR(200);
ALTER TABLE MENSAGEM ADD ARQUIVO_NOME VARCHAR(200) CHARACTER SET UTF8;
ALTER TABLE MENSAGEM ADD ARQUIVO_TIPO VARCHAR(50);
ALTER TABLE MENSAGEM ADD ARQUIVO_TAMANHO INTEGER;
