-- ====================================================
-- APPLE SIGN-IN DATABASE MIGRATION
-- Sadece gerekli değişiklikler
-- ====================================================

-- 1. USERS TABLOSUNA APPLE İÇİN GEREKLİ SÜTUNLARI EKLE
-- ====================================================

-- Apple ID için (Google ID gibi)
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS apple_id VARCHAR(255);

-- Apple'ın verdiği private email için
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS apple_private_email VARCHAR(255);

-- Bu email'in Apple'dan gelip gelmediğini bilmek için
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS is_apple_provided_email BOOLEAN DEFAULT FALSE;

-- Hangi provider ile giriş yaptığını track etmek için
ALTER TABLE users 
ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'google';
-- Değerler: 'google', 'apple', 'email', 'facebook'

-- 2. INDEX'LERİ EKLE (PERFORMANS İÇİN)
-- ====================================================

-- Apple ID ile hızlı lookup için
CREATE INDEX IF NOT EXISTS idx_users_apple_id 
ON users(apple_id) WHERE apple_id IS NOT NULL;

-- Auth provider ile sorgular için
CREATE INDEX IF NOT EXISTS idx_users_auth_provider 
ON users(auth_provider);

-- Apple email'leri için
CREATE INDEX IF NOT EXISTS idx_users_apple_email 
ON users(apple_private_email) WHERE apple_private_email IS NOT NULL;

-- 3. APPLE SIGN-IN İÇİN YENİ FUNCTION
-- ====================================================
CREATE OR REPLACE FUNCTION upsert_user_from_apple(
    p_apple_id VARCHAR(255),
    p_email CITEXT,
    p_full_name VARCHAR(100),
    p_is_private_email BOOLEAN DEFAULT FALSE,
    p_metadata JSONB DEFAULT NULL
)
RETURNS TABLE(
    user_id UUID,
    role user_role,
    is_active BOOLEAN,
    is_new_user BOOLEAN,
    auth_provider VARCHAR(20)
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_user_id UUID;
    v_is_new BOOLEAN := FALSE;
    v_existing_email CITEXT;
BEGIN
    -- Önce apple_id ile ara
    SELECT id, email INTO v_user_id, v_existing_email
    FROM users 
    WHERE apple_id = p_apple_id;
    
    -- Apple ID yoksa, email ile ara (private email de olabilir)
    IF v_user_id IS NULL AND p_email IS NOT NULL THEN
        SELECT id, email INTO v_user_id, v_existing_email
        FROM users 
        WHERE email = p_email;
    END IF;
    
    IF v_user_id IS NULL THEN
        -- YENİ KULLANICI (Apple ile ilk giriş)
        v_is_new := TRUE;
        
        INSERT INTO users (
            apple_id,
            email,
            apple_private_email,
            is_apple_provided_email,
            full_name,
            auth_provider,
            last_login_at,
            last_active_at,
            metadata,
            is_verified  -- Apple'dan gelenler verified sayılır
        )
        VALUES (
            p_apple_id,
            p_email,  -- Apple'ın verdiği email (private veya normal)
            CASE 
                WHEN p_is_private_email THEN p_email
                ELSE NULL
            END,
            p_is_private_email,
            p_full_name,
            'apple',
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            COALESCE(p_metadata, jsonb_build_object(
                'source', 'apple_oauth',
                'is_private_email', p_is_private_email
            )),
            TRUE  -- Apple ile gelenler verified
        )
        RETURNING id INTO v_user_id;
        
    ELSE
        -- VAR OLAN KULLANICI - Update et
        UPDATE users
        SET 
            apple_id = COALESCE(p_apple_id, apple_id),
            email = CASE 
                WHEN is_apple_provided_email = FALSE THEN p_email
                ELSE email  -- Apple private email'i değiştirme
            END,
            apple_private_email = CASE 
                WHEN p_is_private_email THEN p_email
                ELSE apple_private_email
            END,
            is_apple_provided_email = p_is_private_email,
            full_name = COALESCE(p_full_name, full_name),
            last_login_at = CURRENT_TIMESTAMP,
            last_active_at = CURRENT_TIMESTAMP,
            auth_provider = 'apple',
            updated_at = CURRENT_TIMESTAMP,
            metadata = COALESCE(p_metadata, metadata),
            is_verified = TRUE  -- Apple ile giriş yapınca verified yap
        WHERE id = v_user_id;
    END IF;
    
    RETURN QUERY
    SELECT 
        u.id,
        u.role,
        u.is_active,
        v_is_new,
        u.auth_provider
    FROM users u
    WHERE u.id = v_user_id;
END;
$$;

-- 4. MEVCUT GOOGLE FUNCTION'INI GÜNCELLE (OPSİYONEL)
-- ====================================================
CREATE OR REPLACE FUNCTION upsert_user_from_google(
    p_google_id VARCHAR(255),
    p_email CITEXT,
    p_full_name VARCHAR(100),
    p_avatar_url TEXT DEFAULT NULL,
    p_locale VARCHAR(10) DEFAULT 'tr_TR',
    p_metadata JSONB DEFAULT NULL
)
RETURNS TABLE(
    user_id UUID,
    role user_role,
    is_active BOOLEAN,
    is_new_user BOOLEAN,
    stripe_account_id VARCHAR(255)
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_user_id UUID;
    v_is_new BOOLEAN := FALSE;
    v_existing_stripe_id VARCHAR(255);
BEGIN
    -- Try to find by google_id first
    SELECT u.id, u.stripe_account_id
    INTO v_user_id, v_existing_stripe_id
    FROM users u
    WHERE u.google_id = p_google_id;
    
    IF v_user_id IS NULL THEN
        -- Try by email (in case google_id changed)
        SELECT u.id, u.stripe_account_id
        INTO v_user_id, v_existing_stripe_id
        FROM users u
        WHERE u.email = p_email;
    END IF;
    
    IF v_user_id IS NULL THEN
        -- NEW USER
        v_is_new := TRUE;
        
        INSERT INTO users (
            google_id,
            email,
            full_name,
            avatar_url,
            locale,
            last_login_at,
            last_active_at,
            metadata,
            auth_provider,
            is_verified
        )
        VALUES (
            p_google_id,
            p_email,
            p_full_name,
            p_avatar_url,
            p_locale,
            CURRENT_TIMESTAMP,
            CURRENT_TIMESTAMP,
            COALESCE(p_metadata, '{"source": "google_oauth"}'::jsonb),
            'google',
            TRUE  -- Google ile gelenler verified
        )
        RETURNING id INTO v_user_id;
        
    ELSE
        -- EXISTING USER - Update
        UPDATE users
        SET 
            google_id = COALESCE(p_google_id, google_id),
            email = p_email,
            full_name = COALESCE(p_full_name, full_name),
            avatar_url = COALESCE(p_avatar_url, avatar_url),
            locale = COALESCE(p_locale, locale),
            last_login_at = CURRENT_TIMESTAMP,
            last_active_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            metadata = COALESCE(p_metadata, metadata),
            auth_provider = 'google',
            is_verified = TRUE
        WHERE id = v_user_id;
    END IF;
    
    -- Return result
    RETURN QUERY
    SELECT 
        u.id,
        u.role,
        u.is_active,
        v_is_new,
        u.stripe_account_id
    FROM users u
    WHERE u.id = v_user_id;
END;
$$;

-- 5. USER SESSIONS TABLOSUNA AUTH PROVIDER EKLE (OPSİYONEL)
-- ====================================================
ALTER TABLE user_sessions 
ADD COLUMN IF NOT EXISTS auth_provider VARCHAR(20) DEFAULT 'google';

-- 6. TEST İÇİN BİRKAÇ APPLE KULLANICISI EKLE (OPSİYONEL)
-- ====================================================
INSERT INTO users (
    email,
    apple_id,
    apple_private_email,
    is_apple_provided_email,
    full_name,
    auth_provider,
    role,
    is_active,
    is_verified
) VALUES 
(
    'user_privaterelay@appleid.com',
    'apple_001_ios_user',
    'user_privaterelay@appleid.com',
    TRUE,
    'iOS User 1',
    'apple',
    'user',
    TRUE,
    TRUE
),
(
    'john_doe@icloud.com',
    'apple_002_john',
    NULL,  -- Private email değil
    FALSE,
    'John Doe',
    'apple',
    'user',
    TRUE,
    TRUE
) ON CONFLICT (email) DO NOTHING;

-- 7. SON KONTROL VE MESAJ
-- ====================================================
DO $$
BEGIN
    RAISE NOTICE '=========================================';
    RAISE NOTICE '✅ APPLE SIGN-IN MIGRATION TAMAMLANDI!';
    RAISE NOTICE '=========================================';
    RAISE NOTICE 'Eklenen Sütunlar:';
    RAISE NOTICE '1. apple_id';
    RAISE NOTICE '2. apple_private_email';
    RAISE NOTICE '3. is_apple_provided_email';
    RAISE NOTICE '4. auth_provider';
    RAISE NOTICE '';
    RAISE NOTICE 'Eklenen Indexler:';
    RAISE NOTICE '1. idx_users_apple_id';
    RAISE NOTICE '2. idx_users_auth_provider';
    RAISE NOTICE '3. idx_users_apple_email';
    RAISE NOTICE '';
    RAISE NOTICE 'Eklenen Function:';
    RAISE NOTICE '1. upsert_user_from_apple()';
    RAISE NOTICE '';
    RAISE NOTICE 'Güncellenen Function:';
    RAISE NOTICE '1. upsert_user_from_google()';
    RAISE NOTICE '=========================================';
END $$;


