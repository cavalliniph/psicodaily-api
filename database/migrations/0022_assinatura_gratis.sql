-- 9: quem ja era profissional ganha 30 dias de Essencial gratis, para ninguem sumir da busca no deploy.
INSERT INTO ASSINATURA (PROFISSIONAL_ID, PLANO, VALIDA_ATE)
SELECT USUARIO_ID, 'ESSENCIAL', DATEADD(30 DAY TO CURRENT_DATE) FROM PROFISSIONAL;
