-- 17: boleto e cartao pela Arkhé. Pix e boleto saem da tabela COBRANCA dela, mas a venda no cartao tem o id
-- da tabela COMPRA, que pode repetir o de uma cobranca: o id so e unico dentro do metodo.
ALTER TABLE PAGAMENTO DROP CONSTRAINT UQ_PAGAMENTO_COBRANCA;
ALTER TABLE PAGAMENTO ADD CONSTRAINT UQ_PAGAMENTO_METODO_COBRANCA UNIQUE (METODO, ID_COBRANCA_ARKHE);
ALTER TABLE PAGAMENTO ADD CONSTRAINT CK_PAGAMENTO_METODO CHECK (METODO IN ('PIX', 'BOLETO', 'CARTAO'));
