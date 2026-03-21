-- ====================================================
-- CRAFTORA MIGRATION v2.0
-- BU DOSYAYI MEVCUT DATABASE'DE ÇALIŞTIR
-- ====================================================

-- 1. MEVCUT TABLOLARA EKLEMELER YAPALIM
-- ====================================================

-- A) ÖNCE GEREKLİ SÜTUNLARI KONTROL ET VE EKLE
DO $$ 
BEGIN
    -- shops tablosunda metadata sütunu var mı kontrol et
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'metadata'
    ) THEN
        ALTER TABLE shops 
        ADD COLUMN metadata JSONB DEFAULT '{}'::jsonb;
        
        RAISE NOTICE '✅ Shops tablosuna metadata sütunu eklendi';
    ELSE
        RAISE NOTICE '⚠️  Shops metadata sütunu zaten var';
    END IF;
END $$;

-- B) SHOPS TABLOSUNA PAUSE SÜTUNLARI EKLE
DO $$ 
BEGIN
    -- Sütun var mı kontrol et, yoksa ekle
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'is_paused'
    ) THEN
        ALTER TABLE shops 
        ADD COLUMN is_paused BOOLEAN DEFAULT FALSE,
        ADD COLUMN paused_at TIMESTAMPTZ,
        ADD COLUMN paused_until TIMESTAMPTZ,
        ADD COLUMN pause_reason TEXT,
        ADD COLUMN auto_resume_date TIMESTAMPTZ;
        
        RAISE NOTICE '✅ Shops tablosuna pause sütunları eklendi';
    ELSE
        RAISE NOTICE '⚠️  Pause sütunları zaten var';
    END IF;
END $$;

-- C) PRODUCTS TABLOSUNA PLATFORM İŞARETİ EKLE
DO $$
BEGIN
    -- Önce metadata sütunu var mı kontrol et
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'products' AND column_name = 'metadata'
    ) THEN
        -- Mevcut tüm ürünlere platform işareti ekle
        UPDATE products 
        SET metadata = COALESCE(metadata, '{}'::jsonb) || '{"is_platform_product": false}'::jsonb
        WHERE metadata->>'is_platform_product' IS NULL;
        
        RAISE NOTICE '✅ Tüm ürünlere platform işareti eklendi';
    ELSE
        RAISE NOTICE '⚠️  Products tablosunda metadata sütunu yok';
    END IF;
END $$;

-- 2. YENİ TABLOLAR OLUŞTURALIM
-- ====================================================

-- A) PAYMENT_REMINDERS TABLOSU
DO $$
BEGIN
    CREATE TABLE IF NOT EXISTS payment_reminders (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        shop_id UUID NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
        
        reminder_type VARCHAR(20) NOT NULL,
        days_until_due INTEGER,
        amount_due DECIMAL(10,2) NOT NULL,
        
        email_sent BOOLEAN DEFAULT FALSE,
        email_sent_at TIMESTAMPTZ,
        email_template VARCHAR(50),
        
        created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
        
        CONSTRAINT valid_reminder_type CHECK (
            reminder_type IN ('warning_30days', 'warning_7days', 'warning_1day', 'suspended', 'banned')
        )
    );
    -- Index ekle
    CREATE INDEX IF NOT EXISTS idx_payment_reminders_shop_id ON payment_reminders(shop_id);
    CREATE INDEX IF NOT EXISTS idx_payment_reminders_created_at ON payment_reminders(created_at DESC);
    RAISE NOTICE '✅ Payment_reminders tablosu oluşturuldu';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE '❌ Payment_reminders tablosu oluşturulamadı: %', SQLERRM;
END $$;

-- 3. PLATFORM (CRAFTORA) RESMİ MAĞAZASI OLUŞTUR
-- ====================================================

DO $$
DECLARE
    v_platform_user_id UUID;
    v_platform_shop_id UUID;
    v_metadata_exists BOOLEAN;
    v_users_metadata_exists BOOLEAN;
BEGIN
    -- users tablosunda metadata sütunu var mı kontrol et
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'users' AND column_name = 'metadata'
    ) INTO v_users_metadata_exists;
    
    -- Platform için admin user oluştur (eğer yoksa)
    IF v_users_metadata_exists THEN
        INSERT INTO users (
            email,
            google_id,
            full_name,
            role,
            is_active,
            is_verified,
            metadata
        ) VALUES (
            'platform@craftora.com',
            'craftora_platform_001',
            'CRAFTORA Platform',
            'admin',
            TRUE,
            TRUE,
            '{"is_platform_account": true, "can_manage_all": true}'::jsonb
        ) ON CONFLICT (email) 
        DO UPDATE SET 
            metadata = EXCLUDED.metadata
        RETURNING id INTO v_platform_user_id;
    ELSE
        INSERT INTO users (
            email,
            google_id,
            full_name,
            role,
            is_active,
            is_verified
        ) VALUES (
            'platform@craftora.com',
            'craftora_platform_001',
            'CRAFTORA Platform',
            'admin',
            TRUE,
            TRUE
        ) ON CONFLICT (email) 
        DO UPDATE SET 
            full_name = EXCLUDED.full_name,
            role = EXCLUDED.role
        RETURNING id INTO v_platform_user_id;
    END IF;
    
    -- shops tablosunda metadata sütunu var mı kontrol et
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'metadata'
    ) INTO v_metadata_exists;
    
    -- Platform mağazası oluştur
    IF v_metadata_exists THEN
        INSERT INTO shops (
            user_id,
            shop_name,
            slug,
            description,
            subscription_status,
            monthly_fee,
            is_verified,
            is_featured,
            metadata
        ) VALUES (
            v_platform_user_id,
            'CRAFTORA Official',
            'craftora-official',
            'Official CRAFTORA platform products and services',
            'active',
            0.00,
            TRUE,
            TRUE,
            '{
                "is_platform_shop": true,
                "managed_by": "craftora_admin",
                "cannot_be_suspended": true,
                "platform_commission_exempt": true
            }'::jsonb
        ) ON CONFLICT (slug) 
        DO UPDATE SET 
            shop_name = EXCLUDED.shop_name,
            description = EXCLUDED.description,
            metadata = EXCLUDED.metadata
        RETURNING id INTO v_platform_shop_id;
    ELSE
        INSERT INTO shops (
            user_id,
            shop_name,
            slug,
            description,
            subscription_status,
            monthly_fee,
            is_verified,
            is_featured
        ) VALUES (
            v_platform_user_id,
            'CRAFTORA Official',
            'craftora-official',
            'Official CRAFTORA platform products and services',
            'active',
            0.00,
            TRUE,
            TRUE
        ) ON CONFLICT (slug) 
        DO UPDATE SET 
            shop_name = EXCLUDED.shop_name,
            description = EXCLUDED.description
        RETURNING id INTO v_platform_shop_id;
    END IF;
    
    RAISE NOTICE '✅ Platform mağazası oluşturuldu: %', v_platform_shop_id;
EXCEPTION
    WHEN others THEN
        RAISE NOTICE '❌ Platform mağazası oluşturulamadı: %', SQLERRM;
END $$;

-- 4. TRIGGER'LARI EKLE/GÜNCELLE
-- ====================================================

-- A) PLATFORM ÜRÜN OTOMATİK İŞARETLEME TRIGGER'I
-- 4. TRIGGER'LARI EKLE/GÜNCELLE
-- ====================================================

-- A) PLATFORM ÜRÜN OTOMATİK İŞARETLEME TRIGGER'I
-- 4. TRIGGER'LARI EKLE/GÜNCELLE
-- ====================================================

-- A) PLATFORM ÜRÜN OTOMATİK İŞARETLEME TRIGGER'I

-- ÖNCE FONKSİYONU OLUŞTUR (DO BLOĞUNDAN BAĞIMSIZ)
CREATE OR REPLACE FUNCTION set_platform_product_metadata()
RETURNS TRIGGER AS $$
BEGIN
    -- Eğer shop_id platform shop'u ise, otomatik işaretle
    IF EXISTS (
        SELECT 1 FROM shops 
        WHERE id = NEW.shop_id 
        AND metadata->>'is_platform_shop' = 'true'
    ) THEN
        NEW.metadata = COALESCE(NEW.metadata, '{}'::jsonb) || 
            '{"is_platform_product": true, "managed_by": "platform"}'::jsonb;
        -- requires_approval sütunu varsa
        BEGIN
            NEW.requires_approval = FALSE;
        EXCEPTION WHEN undefined_column THEN
            -- sütun yoksa hata verme
        END;
        -- is_approved sütunu varsa
        BEGIN
            NEW.is_approved = TRUE;
        EXCEPTION WHEN undefined_column THEN
            -- sütun yoksa hata verme
        END;
    ELSE
        NEW.metadata = COALESCE(NEW.metadata, '{}'::jsonb) || 
            '{"is_platform_product": false}'::jsonb;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- SONRA DO BLOĞU İLE TRIGGER KONTROLÜ
DO $$
BEGIN
    -- Önce gerekli sütunlar var mı kontrol et
    IF EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'products' AND column_name = 'metadata'
    ) AND EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'products' AND column_name = 'requires_approval'
    ) THEN
        
        -- Trigger'ı oluştur (eğer yoksa)
        IF NOT EXISTS (
            SELECT 1 FROM pg_trigger 
            WHERE tgname = 'trg_set_platform_product_metadata'
        ) THEN
            CREATE TRIGGER trg_set_platform_product_metadata
                BEFORE INSERT ON products
                FOR EACH ROW
                EXECUTE FUNCTION set_platform_product_metadata();
            
            RAISE NOTICE '✅ Platform product trigger eklendi';
        ELSE
            RAISE NOTICE '⚠️  Platform product trigger zaten var';
        END IF;
    ELSE
        RAISE NOTICE '⚠️  Products tablosunda gerekli sütunlar yok, trigger eklenmedi';
    END IF;
END $$;


-- 5. FONKSİYONLARI EKLE
-- ====================================================

-- A) MAĞAZA DONDURMA FONKSİYONU
CREATE OR REPLACE FUNCTION pause_shop(
    p_shop_id UUID,
    p_pause_days INTEGER DEFAULT 30,
    p_reason TEXT DEFAULT 'seller_request'
)
RETURNS TABLE(
    success BOOLEAN,
    message TEXT,
    paused_until DATE
)
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_shop_status subscription_status;
    v_visibility_exists BOOLEAN;
BEGIN
    -- Mağaza durumunu kontrol et
    SELECT subscription_status INTO v_shop_status
    FROM shops 
    WHERE id = p_shop_id;
    
    IF NOT FOUND THEN
        RETURN QUERY SELECT FALSE, 'Shop not found', NULL::DATE;
        RETURN;
    END IF;
    
    -- Sadece active olan mağazalar dondurulabilir
    IF v_shop_status != 'active' THEN
        RETURN QUERY SELECT FALSE, 'Only active shops can be paused', NULL::DATE;
        RETURN;
    END IF;
    
    -- visibility sütunu var mı kontrol et
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'visibility'
    ) INTO v_visibility_exists;
    
    -- Dondurma işlemi
    IF v_visibility_exists THEN
        UPDATE shops
        SET 
            is_paused = TRUE,
            paused_at = CURRENT_TIMESTAMP,
            paused_until = CURRENT_TIMESTAMP + (p_pause_days || ' days')::INTERVAL,
            pause_reason = p_reason,
            auto_resume_date = CURRENT_TIMESTAMP + (p_pause_days || ' days')::INTERVAL,
            visibility = 'private',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = p_shop_id;
    ELSE
        UPDATE shops
        SET 
            is_paused = TRUE,
            paused_at = CURRENT_TIMESTAMP,
            paused_until = CURRENT_TIMESTAMP + (p_pause_days || ' days')::INTERVAL,
            pause_reason = p_reason,
            auto_resume_date = CURRENT_TIMESTAMP + (p_pause_days || ' days')::INTERVAL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = p_shop_id;
    END IF;
    
    -- Tüm ürünleri geçici olarak görünmez yap
    UPDATE products
    SET status = 'draft'
    WHERE shop_id = p_shop_id
        AND status = 'published';
    
    RETURN QUERY SELECT TRUE, 'Shop paused successfully', 
        (CURRENT_DATE + p_pause_days);
END;
$$;

-- B) MAĞAZA DEVAM ETTİRME FONKSİYONU
CREATE OR REPLACE FUNCTION resume_shop(p_shop_id UUID)
RETURNS BOOLEAN
LANGUAGE plpgsql
SECURITY DEFINER
AS $$
DECLARE
    v_visibility_exists BOOLEAN;
BEGIN
    -- visibility sütunu var mı kontrol et
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'visibility'
    ) INTO v_visibility_exists;
    
    IF v_visibility_exists THEN
        UPDATE shops
        SET 
            is_paused = FALSE,
            paused_until = NULL,
            auto_resume_date = NULL,
            visibility = 'public',
            updated_at = CURRENT_TIMESTAMP
        WHERE id = p_shop_id;
    ELSE
        UPDATE shops
        SET 
            is_paused = FALSE,
            paused_until = NULL,
            auto_resume_date = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = p_shop_id;
    END IF;
    
    -- Ürünleri tekrar yayınla
    UPDATE products
    SET status = 'published'
    WHERE shop_id = p_shop_id
        AND status = 'draft';
    
    RETURN FOUND;
END;
$$;

-- C) OTOMATİK ÖDEME HATIRLATMA FONKSİYONU
CREATE OR REPLACE FUNCTION process_payment_reminders()
RETURNS TABLE(
    reminders_created INTEGER,
    emails_sent INTEGER,
    shops_suspended INTEGER,
    shops_banned INTEGER
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_reminders_created INTEGER := 0;
    v_emails_sent INTEGER := 0;
    v_shops_suspended INTEGER := 0;
    v_shops_banned INTEGER := 0;
    v_next_payment_exists BOOLEAN;
    v_grace_period_exists BOOLEAN;
BEGIN
    -- shops tablosunda gerekli sütunlar var mı kontrol et
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'next_payment_due_date'
    ) INTO v_next_payment_exists;
    
    SELECT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'shops' AND column_name = 'grace_period_end_date'
    ) INTO v_grace_period_exists;
    
    IF NOT v_next_payment_exists THEN
        RAISE NOTICE '⚠️  next_payment_due_date sütunu eksik, fonksiyon çalıştırılamadı';
        RETURN QUERY SELECT 0, 0, 0, 0;
        RETURN;
    END IF;
    
    -- 1. 30 GÜN KALA UYARI
    INSERT INTO payment_reminders (shop_id, reminder_type, days_until_due, amount_due)
    SELECT 
        s.id,
        'warning_30days',
        (s.next_payment_due_date - CURRENT_DATE),
        10.00
    FROM shops s
    WHERE s.subscription_status = 'active'
        AND s.next_payment_due_date = CURRENT_DATE + INTERVAL '30 days'
        AND (s.metadata->>'is_platform_shop' IS DISTINCT FROM 'true' OR s.metadata IS NULL)
        AND NOT EXISTS (
            SELECT 1 FROM payment_reminders pr 
            WHERE pr.shop_id = s.id 
            AND pr.reminder_type = 'warning_30days'
            AND DATE(pr.created_at) = CURRENT_DATE
        );
    
    GET DIAGNOSTICS v_reminders_created = ROW_COUNT;
    
    -- 2. 7 GÜN KALA UYARI
    INSERT INTO payment_reminders (shop_id, reminder_type, days_until_due, amount_due)
    SELECT 
        s.id,
        'warning_7days',
        (s.next_payment_due_date - CURRENT_DATE),
        10.00
    FROM shops s
    WHERE s.subscription_status = 'active'
        AND s.next_payment_due_date = CURRENT_DATE + INTERVAL '7 days'
        AND (s.metadata->>'is_platform_shop' IS DISTINCT FROM 'true' OR s.metadata IS NULL)
        AND NOT EXISTS (
            SELECT 1 FROM payment_reminders pr 
            WHERE pr.shop_id = s.id 
            AND pr.reminder_type = 'warning_7days'
        );
    
    -- 3. 1 GÜN KALA SON UYARI
    INSERT INTO payment_reminders (shop_id, reminder_type, days_until_due, amount_due)
    SELECT 
        s.id,
        'warning_1day',
        (s.next_payment_due_date - CURRENT_DATE),
        10.00
    FROM shops s
    WHERE s.subscription_status = 'active'
        AND s.next_payment_due_date = CURRENT_DATE + INTERVAL '1 day'
        AND (s.metadata->>'is_platform_shop' IS DISTINCT FROM 'true' OR s.metadata IS NULL);
    
    -- 4. ÖDEME GECİKMİŞSE - SUSPEND (30 gün geçmiş)
    IF v_grace_period_exists THEN
        WITH suspended_shops AS (
            UPDATE shops
            SET subscription_status = 'suspended',
                grace_period_end_date = CURRENT_DATE + INTERVAL '15 days',
                updated_at = CURRENT_TIMESTAMP
            WHERE subscription_status = 'active'
                AND next_payment_due_date < CURRENT_DATE - INTERVAL '30 days'
                AND (metadata->>'is_platform_shop' IS DISTINCT FROM 'true' OR metadata IS NULL)
            RETURNING id
        )
        INSERT INTO payment_reminders (shop_id, reminder_type, days_until_due, amount_due)
        SELECT 
            ss.id,
            'suspended',
            EXTRACT(DAY FROM (CURRENT_DATE - s.next_payment_due_date))::INTEGER * -1,
            10.00
        FROM suspended_shops ss
        JOIN shops s ON ss.id = s.id;
    ELSE
        WITH suspended_shops AS (
            UPDATE shops
            SET subscription_status = 'suspended',
                updated_at = CURRENT_TIMESTAMP
            WHERE subscription_status = 'active'
                AND next_payment_due_date < CURRENT_DATE - INTERVAL '30 days'
                AND (metadata->>'is_platform_shop' IS DISTINCT FROM 'true' OR metadata IS NULL)
            RETURNING id
        )
        INSERT INTO payment_reminders (shop_id, reminder_type, days_until_due, amount_due)
        SELECT 
            ss.id,
            'suspended',
            EXTRACT(DAY FROM (CURRENT_DATE - s.next_payment_due_date))::INTEGER * -1,
            10.00
        FROM suspended_shops ss
        JOIN shops s ON ss.id = s.id;
    END IF;
    
    GET DIAGNOSTICS v_shops_suspended = ROW_COUNT;
    
    -- 5. SUSPEND'DEN BANNED'E (45 gün geçmiş)
    IF v_grace_period_exists THEN
        WITH banned_shops AS (
            UPDATE shops
            SET subscription_status = 'banned',
                updated_at = CURRENT_TIMESTAMP
            WHERE subscription_status = 'suspended'
                AND next_payment_due_date < CURRENT_DATE - INTERVAL '45 days'
                AND (grace_period_end_date IS NULL OR grace_period_end_date < CURRENT_DATE)
                AND (metadata->>'is_platform_shop' IS DISTINCT FROM 'true' OR metadata IS NULL)
            RETURNING id
        )
        INSERT INTO payment_reminders (shop_id, reminder_type, days_until_due, amount_due)
        SELECT 
            bs.id,
            'banned',
            EXTRACT(DAY FROM (CURRENT_DATE - s.next_payment_due_date))::INTEGER * -1,
            10.00
        FROM banned_shops bs
        JOIN shops s ON bs.id = s.id;
    ELSE
        WITH banned_shops AS (
            UPDATE shops
            SET subscription_status = 'banned',
                updated_at = CURRENT_TIMESTAMP
            WHERE subscription_status = 'suspended'
                AND next_payment_due_date < CURRENT_DATE - INTERVAL '45 days'
                AND (metadata->>'is_platform_shop' IS DISTINCT FROM 'true' OR metadata IS NULL)
            RETURNING id
        )
        INSERT INTO payment_reminders (shop_id, reminder_type, days_until_due, amount_due)
        SELECT 
            bs.id,
            'banned',
            EXTRACT(DAY FROM (CURRENT_DATE - s.next_payment_due_date))::INTEGER * -1,
            10.00
        FROM banned_shops bs
        JOIN shops s ON bs.id = s.id;
    END IF;
    
    GET DIAGNOSTICS v_shops_banned = ROW_COUNT;
    
    -- 6. EMAIL GÖNDERİLECEKLERİ İŞARETLE
    UPDATE payment_reminders
    SET 
        email_sent = TRUE,
        email_sent_at = CURRENT_TIMESTAMP,
        email_template = CASE reminder_type
            WHEN 'warning_30days' THEN 'payment_reminder_30days'
            WHEN 'warning_7days' THEN 'payment_reminder_7days'
            WHEN 'warning_1day' THEN 'payment_reminder_1day'
            WHEN 'suspended' THEN 'account_suspended'
            WHEN 'banned' THEN 'account_banned'
        END
    WHERE email_sent = FALSE
        AND created_at >= CURRENT_DATE;
    
    GET DIAGNOSTICS v_emails_sent = ROW_COUNT;
    
    RETURN QUERY SELECT 
        v_reminders_created,
        v_emails_sent,
        v_shops_suspended,
        v_shops_banned;
END;
$$;

-- D) OTOMATİK RESUME FONKSİYONU
CREATE OR REPLACE FUNCTION auto_resume_paused_shops()
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_resumed_count INTEGER := 0;
BEGIN
    WITH shops_to_resume AS (
        SELECT id
        FROM shops
        WHERE is_paused = TRUE
            AND auto_resume_date IS NOT NULL
            AND auto_resume_date <= CURRENT_TIMESTAMP
    )
    SELECT COUNT(*) INTO v_resumed_count
    FROM shops_to_resume;
    
    -- Otomatik devam ettir
    PERFORM resume_shop(id)
    FROM shops
    WHERE is_paused = TRUE
        AND auto_resume_date IS NOT NULL
        AND auto_resume_date <= CURRENT_TIMESTAMP;
    
    RETURN v_resumed_count;
END;
$$;

-- 6. VIEW'LAR OLUŞTUR (ADMIN PANEL İÇİN)
-- ====================================================

-- A) ADMIN USERS VIEW
-- B) ADMIN SHOPS VIEW
DO $$
BEGIN
    CREATE OR REPLACE VIEW admin_shops_view AS
    SELECT 
        -- shops tablosundaki tüm sütunları açıkça listele (total_products hariç)
        s.id,
        s.user_id,
        s.shop_name,
        s.slug,
        s.description,
        s.logo_url,
        s.banner_url,
        s.website_url,
        s.social_links,
        s.subscription_status,
        s.monthly_fee,
        s.next_payment_due_date,
        s.grace_period_end_date,
        s.total_sales,
        s.total_revenue,
        s.is_verified,
        s.is_featured,
        s.visibility,
        s.is_paused,
        s.paused_at,
        s.paused_until,
        s.pause_reason,
        s.auto_resume_date,
        s.metadata,
        s.created_at,
        s.updated_at,
        
        u.email as owner_email,
        u.full_name as owner_name,
        u.created_at as owner_since,
        
        -- Ödeme durumu
        CASE 
            WHEN s.subscription_status = 'active' AND s.next_payment_due_date > CURRENT_DATE THEN 'paid'
            WHEN s.subscription_status = 'active' AND s.next_payment_due_date <= CURRENT_DATE THEN 'payment_due'
            WHEN s.subscription_status = 'suspended' THEN 'suspended'
            WHEN s.subscription_status = 'banned' THEN 'banned'
            ELSE 'unknown'
        END as payment_status,
        
        -- Geç kalan gün sayısı
        CASE 
            WHEN s.subscription_status = 'active' AND s.next_payment_due_date <= CURRENT_DATE 
            THEN EXTRACT(DAY FROM (CURRENT_DATE - s.next_payment_due_date))::INTEGER
            ELSE 0
        END as days_overdue,
        
        -- Ürün istatistikleri (shops tablosundaki total_products ile çakışmaması için farklı isim ver)
        (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id) as product_count,
        (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id AND p.status = 'published') as active_product_count,
        
        -- Satış istatistikleri (son 30 gün)
        (SELECT COUNT(*) FROM orders o WHERE o.shop_id = s.id 
            AND o.status = 'completed' 
            AND o.created_at >= CURRENT_DATE - INTERVAL '30 days') as sales_last_30days,
        
        (SELECT COALESCE(SUM(o.order_total), 0) FROM orders o WHERE o.shop_id = s.id 
            AND o.status = 'completed' 
            AND o.created_at >= CURRENT_DATE - INTERVAL '30 days') as revenue_last_30days
        
    FROM shops s
    JOIN users u ON s.user_id = u.id
    ORDER BY s.created_at DESC;
    
    RAISE NOTICE '✅ Admin shops view oluşturuldu';
EXCEPTION
    WHEN undefined_column THEN
        RAISE NOTICE '⚠️  Gerekli sütunlar eksik, basit admin shops view oluşturuluyor';
        
        CREATE OR REPLACE VIEW admin_shops_view AS
        SELECT 
            s.*,
            u.email as owner_email,
            u.full_name as owner_name,
            u.created_at as owner_since,
            NULL as payment_status,
            0 as days_overdue,
            (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id) as product_count,
            0 as active_product_count,
            0 as sales_last_30days,
            0 as revenue_last_30days
        FROM shops s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC;
END $$;

-- B) ADMIN SHOPS VIEW
DO $$
BEGIN
    -- Önce view'ı sil (eğer varsa)
    DROP VIEW IF EXISTS admin_shops_view;
    
    -- Yeni view'ı oluştur (sütun isimlerini değiştirerek)
    CREATE VIEW admin_shops_view AS
    SELECT 
        s.*,
        u.email as owner_email,
        u.full_name as owner_name,
        u.created_at as owner_since,
        
        -- Ödeme durumu
        CASE 
            WHEN s.subscription_status = 'active' AND s.next_payment_due_date > CURRENT_DATE THEN 'paid'
            WHEN s.subscription_status = 'active' AND s.next_payment_due_date <= CURRENT_DATE THEN 'payment_due'
            WHEN s.subscription_status = 'suspended' THEN 'suspended'
            WHEN s.subscription_status = 'banned' THEN 'banned'
            ELSE 'unknown'
        END as payment_status,
        
        -- Geç kalan gün sayısı
        CASE 
            WHEN s.subscription_status = 'active' AND s.next_payment_due_date <= CURRENT_DATE 
            THEN EXTRACT(DAY FROM (CURRENT_DATE - s.next_payment_due_date))::INTEGER
            ELSE 0
        END as days_overdue,
        
        -- Ürün istatistikleri (farklı isimler kullan)
        (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id) as calculated_total_products,
        (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id AND p.status = 'published') as published_products_count,
        
        -- Satış istatistikleri (son 30 gün)
        (SELECT COUNT(*) FROM orders o WHERE o.shop_id = s.id 
            AND o.status = 'completed' 
            AND o.created_at >= CURRENT_DATE - INTERVAL '30 days') as recent_sales_count,
        
        (SELECT COALESCE(SUM(o.order_total), 0) FROM orders o WHERE o.shop_id = s.id 
            AND o.status = 'completed' 
            AND o.created_at >= CURRENT_DATE - INTERVAL '30 days') as recent_revenue
        
    FROM shops s
    JOIN users u ON s.user_id = u.id
    ORDER BY s.created_at DESC;
    
    RAISE NOTICE '✅ Admin shops view oluşturuldu';
EXCEPTION
    WHEN others THEN
        RAISE NOTICE '❌ Admin shops view oluşturulamadı: %', SQLERRM;
        
        -- Basit versiyon oluştur (sütun isimlerini değiştirerek)
        DROP VIEW IF EXISTS admin_shops_view;
        
        CREATE VIEW admin_shops_view AS
        SELECT 
            s.*,
            u.email as owner_email,
            u.full_name as owner_name,
            u.created_at as owner_since,
            NULL::text as payment_status,
            0 as days_overdue,
            (SELECT COUNT(*) FROM products p WHERE p.shop_id = s.id) as calculated_product_count,
            0 as published_products_count,
            0 as recent_sales_count,
            0.00 as recent_revenue
        FROM shops s
        JOIN users u ON s.user_id = u.id
        ORDER BY s.created_at DESC;
        
        RAISE NOTICE '✅ Basit admin shops view oluşturuldu';
END $$;

-- 7. TEST VERİLERİ EKLE (İSTEĞE BAĞLI)
-- ====================================================

DO $$
DECLARE
    v_platform_shop_id UUID;
    v_test_product_id UUID;
    v_requires_approval_exists BOOLEAN;
    v_is_approved_exists BOOLEAN;
BEGIN
    -- Platform mağaza ID'sini al
    SELECT id INTO v_platform_shop_id 
    FROM shops 
    WHERE slug = 'craftora-official';
    
    IF v_platform_shop_id IS NOT NULL THEN
        -- Gerekli sütunlar var mı kontrol et
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'products' AND column_name = 'requires_approval'
        ) INTO v_requires_approval_exists;
        
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns 
            WHERE table_name = 'products' AND column_name = 'is_approved'
        ) INTO v_is_approved_exists;
        
        -- Platforma örnek ürün ekle (eğer yoksa)
        IF v_requires_approval_exists AND v_is_approved_exists THEN
            INSERT INTO products (
                shop_id,
                name,
                slug,
                base_price,
                product_type,
                primary_category,
                description,
                status,
                is_approved,
                requires_approval,
                metadata
            ) VALUES (
                v_platform_shop_id,
                'CRAFTORA Premium Membership',
                'craftora-premium-membership',
                99.99,
                'service',
                'membership',
                'Get access to exclusive CRAFTORA features and benefits',
                'published',
                TRUE,
                FALSE,
                '{"is_platform_product": true, "featured": true, "membership_level": "premium"}'::jsonb
            ) ON CONFLICT (slug) DO NOTHING
            RETURNING id INTO v_test_product_id;
        ELSE
            INSERT INTO products (
                shop_id,
                name,
                slug,
                base_price,
                product_type,
                primary_category,
                description,
                status,
                metadata
            ) VALUES (
                v_platform_shop_id,
                'CRAFTORA Premium Membership',
                'craftora-premium-membership',
                99.99,
                'service',
                'membership',
                'Get access to exclusive CRAFTORA features and benefits',
                'published',
                '{"is_platform_product": true, "featured": true, "membership_level": "premium"}'::jsonb
            ) ON CONFLICT (slug) DO NOTHING
            RETURNING id INTO v_test_product_id;
        END IF;
        
        IF v_test_product_id IS NOT NULL THEN
            RAISE NOTICE '✅ Platform ürünü eklendi: %', v_test_product_id;
        ELSE
            RAISE NOTICE '⚠️  Platform ürünü zaten var veya eklenemedi';
        END IF;
    ELSE
        RAISE NOTICE '⚠️  Platform mağazası bulunamadı, test ürünü eklenmedi';
    END IF;
EXCEPTION
    WHEN others THEN
        RAISE NOTICE '❌ Test ürünü eklenemedi: %', SQLERRM;
END $$;

-- 8. SON KONTROL
-- ====================================================

DO $$
BEGIN
    RAISE NOTICE '=========================================';
    RAISE NOTICE '✅ MIGRATION v2.0 TAMAMLANDI!';
    RAISE NOTICE '=========================================';
    RAISE NOTICE 'Eklenen Özellikler:';
    RAISE NOTICE '1. Platform (CRAFTORA) resmi mağazası';
    RAISE NOTICE '2. Mağaza dondurma/durdurma sistemi';
    RAISE NOTICE '3. Otomatik ödeme hatırlatmaları';
    RAISE NOTICE '4. Admin panel view''ları';
    RAISE NOTICE '5. Platform vs seller ürün ayrımı';
    RAISE NOTICE '=========================================';
END $$;