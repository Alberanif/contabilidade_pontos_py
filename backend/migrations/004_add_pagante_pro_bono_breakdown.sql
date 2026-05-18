-- Adiciona colunas de breakdown pagante/pro_bono em totais de clãs e coaches
ALTER TABLE pontos_ultimate_totais_por_clan
ADD COLUMN IF NOT EXISTS total_pagante INTEGER NOT NULL DEFAULT 0;

ALTER TABLE pontos_ultimate_totais_por_clan
ADD COLUMN IF NOT EXISTS total_pro_bono INTEGER NOT NULL DEFAULT 0;

ALTER TABLE pontos_ultimate_totais_por_coach
ADD COLUMN IF NOT EXISTS total_pagante INTEGER NOT NULL DEFAULT 0;

ALTER TABLE pontos_ultimate_totais_por_coach
ADD COLUMN IF NOT EXISTS total_pro_bono INTEGER NOT NULL DEFAULT 0;
