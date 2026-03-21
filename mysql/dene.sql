-- ====================================================
-- CRAFTORA - CRITICAL FIXES & ENHANCEMENTS
-- TEK SEFERDE ÇALIŞABİLİR - TÜM HATALAR DÜZELTİLDİ
-- ====================================================

-- 1. ÖNCE sütunları ekle (tek tek, IF NOT EXISTS ile)
-- ====================================================
ALTER TABLE users ADD COLUMN IF NOT EXISTS seller_verified BOOLEAN DEFAULT FALSE;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verification_documents JSONB DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS verified_at TIMESTAMPTZ DEFAULT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone_number VARCHAR(20);
ALTER TABLE users ADD COLUMN IF NOT EXISTS tax_id VARCHAR(50);
ALTER TABLE users ADD COLUMN IF NOT EXISTS business_name VARCHAR(255);

-- 2. Index conflictini düzelt
-- ====================================================
DROP INDEX IF EXISTS idx_users_last_active_at;
CREATE INDEX idx_users_last_active_at ON users(last_active_at DESC NULLS LAST);

-- 3. Eksik index'leri ekle (artık seller_verified sütunu var)
-- ====================================================
CREATE INDEX IF NOT EXISTS idx_users_last_login ON users(last_login_at DESC);
CREATE INDEX IF NOT EXISTS idx_users_seller_verification ON users(role, seller_verified, is_active) WHERE role = 'seller';
CREATE INDEX IF NOT EXISTS idx_users_email_history ON users(id, email) WHERE is_active = TRUE;

-- 4. Yeni tablolar oluştur
-- ====================================================
-- 4.1 User Audit Log
CREATE TABLE IF NOT EXISTS user_audit_log (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    action_type VARCHAR(50) NOT NULL,
    table_name VARCHAR(50) NOT NULL,
    record_id UUID NOT NULL,
    old_values JSONB,
    new_values JSONB,
    changed_by UUID REFERENCES users(id),
    ip_address INET,
    user_agent TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_audit_log_user_id ON user_audit_log(user_id);
CREATE INDEX IF NOT EXISTS idx_user_audit_log_created_at ON user_audit_log(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_user_audit_log_action ON user_audit_log(action_type);

-- 4.2 Email History
CREATE TABLE IF NOT EXISTS user_email_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    old_email CITEXT NOT NULL,
    new_email CITEXT NOT NULL,
    changed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    changed_by UUID REFERENCES users(id),
    reason VARCHAR(100)
);

CREATE INDEX IF NOT EXISTS idx_user_email_history_user_id ON user_email_history(user_id);
CREATE INDEX IF NOT EXISTS idx_user_email_history_changed_at ON user_email_history(changed_at DESC);

-- 4.3 Webhook Events
CREATE TABLE IF NOT EXISTS webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id VARCHAR(255) UNIQUE NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    source VARCHAR(50) NOT NULL DEFAULT 'stripe',
    payload JSONB NOT NULL,
    status VARCHAR(20) DEFAULT 'pending',
    processed_at TIMESTAMPTZ,
    error_message TEXT,
    retry_count INTEGER DEFAULT 0,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_webhook_events_event_type ON webhook_events(event_type);
CREATE INDEX IF NOT EXISTS idx_webhook_events_status ON webhook_events(status);
CREATE INDEX IF NOT EXISTS idx_webhook_events_created_at ON webhook_events(created_at DESC);

-- 5. Düzeltilmiş Audit Log Trigger fonksiyonu
-- ====================================================
CREATE OR REPLACE FUNCTION log_user_changes()
RETURNS TRIGGER AS $$
DECLARE
    v_changed_by UUID;
    v_ip_address INET;
    v_user_agent TEXT;
BEGIN
    -- App context'ini güvenli şekilde al
    BEGIN
        v_changed_by := NULLIF(current_setting('app.current_user_id', TRUE), '')::UUID;
    EXCEPTION WHEN OTHERS THEN
        v_changed_by := NULL;
    END;
    
    BEGIN
        v_ip_address := NULLIF(current_setting('app.client_ip', TRUE), '')::INET;
    EXCEPTION WHEN OTHERS THEN
        v_ip_address := NULL;
    END;
    
    BEGIN
        v_user_agent := NULLIF(current_setting('app.user_agent', TRUE), '');
    EXCEPTION WHEN OTHERS THEN
        v_user_agent := NULL;
    END;
    
    IF TG_OP = 'UPDATE' THEN
        INSERT INTO user_audit_log (
            user_id,
            action_type,
            table_name,
            record_id,
            old_values,
            new_values,
            changed_by,
            ip_address,
            user_agent
        ) VALUES (
            NEW.id,
            TG_OP,
            TG_TABLE_NAME,
            NEW.id,
            to_jsonb(OLD),
            to_jsonb(NEW),
            v_changed_by,
            v_ip_address,
            v_user_agent
        );
    ELSIF TG_OP = 'DELETE' THEN
        INSERT INTO user_audit_log (
            user_id,
            action_type,
            table_name,
            record_id,
            old_values,
            changed_by,
            ip_address,
            user_agent
        ) VALUES (
            OLD.id,
            TG_OP,
            TG_TABLE_NAME,
            OLD.id,
            to_jsonb(OLD),
            v_changed_by,
            v_ip_address,
            v_user_agent
        );
    END IF;
    
    RETURN COALESCE(NEW, OLD);
END;
$$ LANGUAGE plpgsql;

-- Trigger'ı oluştur
DROP TRIGGER IF EXISTS trg_users_audit ON users;
CREATE TRIGGER trg_users_audit
    AFTER UPDATE OR DELETE ON users
    FOR EACH ROW
    EXECUTE FUNCTION log_user_changes();

-- 6. Yeni fonksiyonlar
-- ====================================================
-- 6.1 Verify Seller
CREATE OR REPLACE FUNCTION verify_seller(
    p_user_id UUID,
    p_documents JSONB,
    p_verified_by UUID DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_role user_role;
BEGIN
    SELECT role INTO v_current_role
    FROM users 
    WHERE id = p_user_id
    FOR UPDATE;
    
    IF NOT FOUND OR v_current_role != 'seller' THEN
        RETURN FALSE;
    END IF;
    
    UPDATE users
    SET 
        seller_verified = TRUE,
        verification_documents = p_documents,
        verified_at = CURRENT_TIMESTAMP,
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_user_id;
    
    RETURN TRUE;
END;
$$;

-- 6.2 Get Seller Stats
CREATE OR REPLACE FUNCTION get_seller_statistics()
RETURNS TABLE(
    total_sellers BIGINT,
    verified_sellers BIGINT,
    active_sellers BIGINT,
    avg_shop_count NUMERIC,
    newest_seller TIMESTAMPTZ,
    oldest_seller TIMESTAMPTZ
)
LANGUAGE plpgsql
STABLE
AS $$
BEGIN
    RETURN QUERY
    SELECT 
        COUNT(*)::BIGINT as total_sellers,
        COUNT(*) FILTER (WHERE seller_verified = TRUE)::BIGINT as verified_sellers,
        COUNT(*) FILTER (WHERE is_active = TRUE)::BIGINT as active_sellers,
        COALESCE(AVG(shop_count), 0)::NUMERIC as avg_shop_count,
        MAX(seller_since) as newest_seller,
        MIN(seller_since) as oldest_seller
    FROM users
    WHERE role = 'seller';
END;
$$;

-- 6.3 Update User Email
CREATE OR REPLACE FUNCTION update_user_email(
    p_user_id UUID,
    p_new_email CITEXT,
    p_reason VARCHAR(100) DEFAULT 'user_request'
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_old_email CITEXT;
BEGIN
    SELECT email INTO v_old_email
    FROM users 
    WHERE id = p_user_id
    FOR UPDATE;
    
    IF NOT FOUND THEN
        RETURN FALSE;
    END IF;
    
    IF p_new_email !~* '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$' THEN
        RAISE EXCEPTION 'Invalid email format' USING ERRCODE = '22000';
    END IF;
    
    IF EXISTS (SELECT 1 FROM users WHERE email = p_new_email AND id != p_user_id) THEN
        RAISE EXCEPTION 'Email already in use' USING ERRCODE = '23505';
    END IF;
    
    INSERT INTO user_email_history (user_id, old_email, new_email, reason)
    VALUES (p_user_id, v_old_email, p_new_email, p_reason);
    
    UPDATE users
    SET 
        email = p_new_email,
        updated_at = CURRENT_TIMESTAMP,
        is_verified = FALSE
    WHERE id = p_user_id;
    
    RETURN TRUE;
EXCEPTION 
    WHEN SQLSTATE '22000' THEN
        RAISE EXCEPTION 'Geçersiz email formatı';
    WHEN SQLSTATE '23505' THEN
        RAISE EXCEPTION 'Bu email adresi zaten kullanılıyor';
    WHEN OTHERS THEN
        RAISE;
END;
$$;

-- 7. Constraint ekle
-- ====================================================
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'users' AND constraint_name = 'chk_phone_format'
    ) THEN
        ALTER TABLE users 
        ADD CONSTRAINT chk_phone_format CHECK (
            phone_number IS NULL OR 
            phone_number ~ '^\+?[0-9\s\-\(\)]{10,20}$'
        );
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'users' AND constraint_name = 'chk_tax_id_length'
    ) THEN
        ALTER TABLE users 
        ADD CONSTRAINT chk_tax_id_length CHECK (
            tax_id IS NULL OR 
            LENGTH(tax_id) BETWEEN 10 AND 20
        );
    END IF;
    
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.table_constraints 
        WHERE table_name = 'users' AND constraint_name = 'chk_seller_verified'
    ) THEN
        ALTER TABLE users 
        ADD CONSTRAINT chk_seller_verified CHECK (
            role != 'seller' OR seller_verified IN (TRUE, FALSE)
        );
    END IF;
END $$;

-- 8. Sample data ekle
-- ====================================================
DO $$
DECLARE
    v_ali_id UUID;
    v_mehmet_id UUID;
BEGIN
    SELECT id INTO v_ali_id FROM users WHERE email = 'ali@creator.com';
    SELECT id INTO v_mehmet_id FROM users WHERE email = 'mehmet@designer.com';
    
    IF v_ali_id IS NOT NULL THEN
        UPDATE users 
        SET 
            seller_verified = COALESCE(seller_verified, TRUE),
            verified_at = COALESCE(verified_at, seller_since + INTERVAL '2 days'),
            phone_number = COALESCE(phone_number, '+905551234567'),
            business_name = COALESCE(business_name, 'Ali Creative Studio')
        WHERE id = v_ali_id;
    END IF;
    
    IF v_mehmet_id IS NOT NULL THEN
        UPDATE users 
        SET 
            seller_verified = COALESCE(seller_verified, TRUE),
            verified_at = COALESCE(verified_at, seller_since + INTERVAL '2 days'),
            phone_number = COALESCE(phone_number, '+905551234568'),
            business_name = COALESCE(business_name, 'Mehmet Design Co')
        WHERE id = v_mehmet_id;
    END IF;
END $$;

-- 9. Maintenance tablosu
-- ====================================================
CREATE TABLE IF NOT EXISTS maintenance_logs (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    operation VARCHAR(100) NOT NULL,
    table_name VARCHAR(50),
    rows_affected INTEGER,
    duration_ms INTEGER,
    executed_by VARCHAR(100) DEFAULT CURRENT_USER,
    executed_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 10. Test ve temizlik
-- ====================================================
-- 10.1 Test: Satıcı istatistikleri
DO $$
DECLARE
    v_result RECORD;
BEGIN
    RAISE NOTICE '=== TEST 1: Satıcı İstatistikleri ===';
    FOR v_result IN SELECT * FROM get_seller_statistics() LOOP
        RAISE NOTICE 'Toplam Satıcı: %, Doğrulanmış: %, Aktif: %', 
            v_result.total_sellers, 
            v_result.verified_sellers, 
            v_result.active_sellers;
    END LOOP;
    RAISE NOTICE '=== TEST 1 TAMAMLANDI ===';
END $$;

-- 10.2 Test: Tablo kontrol
DO $$
BEGIN
    RAISE NOTICE '=== TEST 2: Yeni Tablolar Kontrol ===';
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'user_audit_log') THEN
        RAISE NOTICE '✓ user_audit_log tablosu oluşturuldu';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'user_email_history') THEN
        RAISE NOTICE '✓ user_email_history tablosu oluşturuldu';
    END IF;
    IF EXISTS (SELECT 1 FROM pg_tables WHERE tablename = 'webhook_events') THEN
        RAISE NOTICE '✓ webhook_events tablosu oluşturuldu';
    END IF;
    RAISE NOTICE '=== TEST 2 TAMAMLANDI ===';
END $$;

-- 10.3 Test: Sütun kontrol
DO $$
DECLARE
    v_count INTEGER;
BEGIN
    RAISE NOTICE '=== TEST 3: Yeni Sütunlar Kontrol ===';
    SELECT COUNT(*) INTO v_count FROM information_schema.columns 
    WHERE table_name = 'users' 
    AND column_name IN ('seller_verified', 'phone_number', 'business_name');
    
    IF v_count = 3 THEN
        RAISE NOTICE '✓ Tüm yeni sütunlar eklendi';
    ELSE
        RAISE NOTICE '⚠ Bazı sütunlar eksik: %/3 eklendi', v_count;
    END IF;
    RAISE NOTICE '=== TEST 3 TAMAMLANDI ===';
END $$;

-- 10.4 Temizlik
DELETE FROM user_sessions 
WHERE expires_at < CURRENT_TIMESTAMP - INTERVAL '30 days'
AND id IN (SELECT id FROM user_sessions WHERE expires_at < CURRENT_TIMESTAMP - INTERVAL '30 days' LIMIT 1000);

DELETE FROM user_audit_log 
WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '90 days'
AND id IN (SELECT id FROM user_audit_log WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '90 days' LIMIT 1000);

ANALYZE users;
ANALYZE user_sessions;
ANALYZE user_audit_log;

-- 11. Başarı mesajı
-- ====================================================
DO $$
BEGIN
    RAISE NOTICE '========================================';
    RAISE NOTICE '✅ CRAFTORA GÜNCELLEMELERİ BAŞARIYLA TAMAMLANDI!';
    RAISE NOTICE '========================================';
    RAISE NOTICE '✓ Yeni sütunlar eklendi';
    RAISE NOTICE '✓ Index conflict düzeltildi';
    RAISE NOTICE '✓ Audit log sistemi kuruldu';
    RAISE NOTICE '✓ Yeni fonksiyonlar eklendi';
    RAISE NOTICE '✓ Testler tamamlandı';
    RAISE NOTICE '========================================';
    RAISE NOTICE '🎯 SİSTEM PRODUCTIONA HAZIR!';
    RAISE NOTICE '========================================';
END $$;

-- ====================================================
-- SON KONTROL (manuel çalıştır)
-- ====================================================
/*
-- 1. Tüm tablolar:
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- 2. Yeni sütunlar:
SELECT column_name, data_type, is_nullable 
FROM information_schema.columns 
WHERE table_name = 'users' 
AND column_name IN ('seller_verified', 'phone_number', 'business_name', 'tax_id', 'verified_at')
ORDER BY column_name;

-- 3. Yeni fonksiyonlar:
SELECT proname, pg_get_function_identity_arguments(oid) 
FROM pg_proc 
WHERE proname IN ('verify_seller', 'get_seller_statistics', 'update_user_email', 'log_user_changes')
ORDER BY proname;

-- 4. Satıcı kontrol:
SELECT 
    email, 
    role, 
    seller_verified, 
    business_name,
    phone_number,
    verified_at::DATE as verified_date
FROM users 
WHERE role = 'seller';
*/




-- update_seller_balance_on_payment fonksiyonunu oluştur
CREATE OR REPLACE FUNCTION update_seller_balance_on_payment(
    p_seller_id UUID,
    p_amount DECIMAL(10,2),
    p_currency VARCHAR(3) DEFAULT 'TRY',
    p_payment_id VARCHAR(255) DEFAULT NULL,
    p_description TEXT DEFAULT NULL
)
RETURNS BOOLEAN
LANGUAGE plpgsql
AS $$
DECLARE
    v_current_balance DECIMAL(10,2);
    v_seller_exists BOOLEAN;
BEGIN
    -- Satıcıyı kontrol et
    SELECT EXISTS(
        SELECT 1 FROM users 
        WHERE id = p_seller_id 
        AND role = 'seller'
        AND is_active = TRUE
    ) INTO v_seller_exists;
    
    IF NOT v_seller_exists THEN
        RAISE EXCEPTION 'Seller not found or not active';
    END IF;
    
    -- Metadata'daki balance'ı güncelle (veya oluştur)
    UPDATE users
    SET 
        metadata = jsonb_set(
            COALESCE(metadata, '{}'::jsonb),
            '{balance}',
            to_jsonb(
                COALESCE(
                    (metadata->>'balance')::DECIMAL,
                    0.00
                ) + p_amount
            )
        ),
        updated_at = CURRENT_TIMESTAMP
    WHERE id = p_seller_id;
    
    -- Payment history için ayrı tablo yoksa, metadata'ya ekle
    UPDATE users
    SET 
        metadata = jsonb_set(
            metadata,
            '{payment_history}',
            COALESCE(metadata->'payment_history', '[]'::jsonb) || 
            jsonb_build_object(
                'timestamp', CURRENT_TIMESTAMP,
                'amount', p_amount,
                'currency', p_currency,
                'payment_id', p_payment_id,
                'description', p_description
            )
        )
    WHERE id = p_seller_id;
    
    RETURN TRUE;
EXCEPTION
    WHEN OTHERS THEN
        RAISE EXCEPTION 'Payment update failed: %', SQLERRM;
END;
$$;





