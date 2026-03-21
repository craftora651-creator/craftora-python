"""
CJ Dropshipping otomasyon servisi
Selenium ile CJ'den API Key alma (Python 3.13 uyumlu)
"""
import logging
from typing import Dict
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
import time
import asyncio

logger = logging.getLogger(__name__)

def _sync_get_api_key(email: str, password: str) -> Dict:
    """
    Senkron olarak CJ'den API Key al (Selenium ile)
    """
    driver = None
    try:
        # Chrome driver'ı kur ve başlat
        options = webdriver.ChromeOptions()
        # Headless modu KAPAT (görmek için)
        # options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        
        logger.info("🚀 Chrome başlatılıyor...")
        driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=options
        )
        
        # 1. Login sayfasına git
        logger.info("🔍 CJ login sayfasına gidiliyor...")
        driver.get('https://www.cjdropshipping.com/login.html')
        time.sleep(10)
         
        WebDriverWait(driver, 10).until(
             EC.presence_of_element_located((By.TAG_NAME, "body"))
             )
        time.sleep(2)
        try:
            cookies = driver.find_elements(By.XPATH, '//button[contains(text(), "Accept") or contains(text(), "Kabul") or contains(text(), "Tamam") or contains(text(), "Allow")]')
            if cookies:
                cookies[0].click()
                time.sleep(1)
                logger.info("🍪 Çerez bildirimi kapatıldı")
        except:
            pass
        
        # Ekran görüntüsü al
        driver.save_screenshot('cj_login.png')
        logger.info("📸 Ekran görüntüsü alındı: cj_login.png")
        
        # 2. Email/Username alanını bul
        logger.info("🔍 Email alanı aranıyor...")
        email_input = None
        
        # Dene 1: name="email"
        try:
            email_input = driver.find_element(By.NAME, 'email')
            logger.info("✅ Email alanı bulundu: By.NAME, 'email'")
        except:
            pass
            
        if not email_input:
            try:
                # Dene 2: input[type="text"]
                email_input = driver.find_element(By.CSS_SELECTOR, 'input[type="text"]')
                logger.info("✅ Email alanı bulundu: input[type='text']")
            except:
                pass
                
        if not email_input:
            try:
                # Dene 3: placeholder ile
                email_input = driver.find_element(By.XPATH, '//input[@placeholder="Username/Email Address"]')
                logger.info("✅ Email alanı bulundu: placeholder ile")
            except:
                pass
                
        if not email_input:
            try:
                # Dene 4: ID ile
                email_input = driver.find_element(By.ID, 'email')
                logger.info("✅ Email alanı bulundu: By.ID, 'email'")
            except:
                pass
                
        if not email_input:
            # Hiçbiri bulunamazsa
            error_msg = "Email input alanı bulunamadı! Sayfa yapısı değişmiş."
            logger.error(f"❌ {error_msg}")
            driver.save_screenshot('cj_error_email.png')
            return {"success": False, "error": error_msg}
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", email_input)
            time.sleep(1)
            driver.execute_script(f"arguments[0].value = '{email}';", email_input)
            logger.info(f"📧 JavaScript ile email girildi: {email[:3]}...{email[-10:] if len(email) > 10 else email}")
        except Exception as js_error:
            logger.warning(f"⚠️ JavaScript ile email girilemedi, normal yöntem deneniyor: {js_error}")
            try:
                email_input.click()
                time.sleep(0.5)
                email_input.clear()
                email_input.send_keys(email)
                logger.info(f"📧 Normal yöntemle email girildi: {email[:3]}...{email[-10:] if len(email) > 10 else email}")
            except Exception as normal_error:
                logger.error(f"❌ Email girilemedi: {normal_error}")
                raise
            time.sleep(1)
        
        # 3. Şifre alanını bul
        logger.info("🔍 Şifre alanı aranıyor...")
        password_input = None
        
        # Dene 1: name="password"
        try:
            password_input = driver.find_element(By.NAME, 'password')
            logger.info("✅ Şifre alanı bulundu: By.NAME, 'password'")
        except:
            pass
            
        if not password_input:
            try:
                # Dene 2: input[type="password"]
                password_input = driver.find_element(By.CSS_SELECTOR, 'input[type="password"]')
                logger.info("✅ Şifre alanı bulundu: input[type='password']")
            except:
                pass
                
        if not password_input:
            try:
                # Dene 3: placeholder ile
                password_input = driver.find_element(By.XPATH, '//input[@placeholder="Password"]')
                logger.info("✅ Şifre alanı bulundu: placeholder ile")
            except:
                pass
                
        if not password_input:
            try:
                # Dene 4: ID ile
                password_input = driver.find_element(By.ID, 'password')
                logger.info("✅ Şifre alanı bulundu: By.ID, 'password'")
            except:
                pass
                
        if not password_input:
            error_msg = "Şifre input alanı bulunamadı!"
            logger.error(f"❌ {error_msg}")
            driver.save_screenshot('cj_error_password.png')
            return {"success": False, "error": error_msg}
        
        try:
            driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", password_input)
            time.sleep(1)
            driver.execute_script(f"arguments[0].value = '{password}';", password_input)
            logger.info("🔑 JavaScript ile şifre girildi")
        except:
            password_input.click()
            time.sleep(0.5)
            password_input.clear()
            password_input.send_keys(password)
            logger.info("🔑 Normal yöntemle şifre girildi")
        time.sleep(1)
        
        # 4. Login butonunu bul
        logger.info("🔍 Login butonu aranıyor...")
        login_btn = None
        
        # Dene 1: İçinde "Sign in" yazıyor
        try:
            login_btn = driver.find_element(By.CSS_SELECTOR, 'div.signin-btn')
            logger.info("✅ Login butonu bulundu: 'Sign in' text")
        except:
            pass
        
        if not login_btn:
            try:
                login_btn = driver.find_element(By.ID, 'login')
                logger.info("✅ Login butonu bulundu: 'Giriş Yap' text")
            except:
                pass
            
        if not login_btn:
            try:
                # Dene 2: type="submit"
                login_btn = driver.find_element(By.XPATH, '//div[contains(@class, "signin") and contains(text(), "Sign in")]')
                logger.info("✅ Login butonu bulundu: button[type='submit']")
            except:
                pass
                
        if not login_btn:
            try:
                # Dene 3: class içinde login geçiyor
                login_btn = driver.find_element(By.CSS_SELECTOR, 'button.login-btn, button.btn-login')
                logger.info("✅ Login butonu bulundu: class ile")
            except:
                pass
                
        if not login_btn:
            try:
                # Dene 4: form içindeki ilk button
                login_btn = driver.find_element(By.CSS_SELECTOR, 'form button')
                logger.info("✅ Login butonu bulundu: form button")
            except:
                pass
        
        if not login_btn:
            try:
                divs = driver.find_elements(By.TAG_NAME, 'div')
                for div in divs:
                    if "Sign in" in div.text and "signin" in div.get_attribute('class'):
                        login_btn = div
                        logger.info("✅ Login butonu bulundu: manuel tarama ile")
                        break
            except:
                pass
                
        if not login_btn:
            error_msg = "Login butonu bulunamadı!"
            logger.error(f"❌ {error_msg}")
            driver.save_screenshot('cj_error_login.png')
            return {"success": False, "error": error_msg}
        
        # Login butonuna tıkla
        login_btn.click()
        logger.info("🔘 Login butonuna tıklandı")
        time.sleep(5)
        
        # 5. API Key sayfasına git
        logger.info("🔍 API Key sayfasına gidiliyor...")
        driver.get('https://www.cjdropshipping.com/my.html#/apikey')
        time.sleep(5)
        
        # 6. API Key'i al
        logger.info("🔍 API Key aranıyor...")
        api_key = None
        
        try:
            api_key_elem = driver.find_element(By.ID, 'apiKeyValue')
            api_key = api_key_elem.get_attribute('value')
            logger.info("✅ API Key bulundu: By.ID")
        except:
            pass
            
        if not api_key:
            try:
                api_key_elem = driver.find_element(By.CSS_SELECTOR, '.api-key-value')
                api_key = api_key_elem.text
                logger.info("✅ API Key bulundu: .api-key-value")
            except:
                pass
        
        if not api_key:
            logger.info("🔑 API Key bulunamadı, sayfada aranıyor...")
            try:
                generate_btn = driver.find_element(By.ID, 'generateApiKey')
                logger.info("✅ Generate butonu bulundu, tıklanıyor...")
                generate_btn.click()
                time.sleep(3)
                try:
                    api_key_elem = driver.find_element(By.ID, 'apiKeyValue')
                    api_key = api_key_elem.get_attribute('value')
                    logger.info("✅ API Key oluşturuldu")
                except:
                    pass
            except:
                logger.info("ℹ️ Generate butonu yok, zaten API Key var mı kontrol ediliyor...")
            if not api_key:
                logger.info("🔍 Sayfada API Key manuel olarak aranıyor...")
                inputs = driver.find_elements(By.TAG_NAME, 'input')
                for i, inp in enumerate(inputs):
                    try:
                        value = inp.get_attribute('value')
                        if value and len(value) > 20 and ("CJ" in value or "@api@" in value):
                            api_key = value
                            logger.info(f"✅ API Key input'ta bulundu: {value[:20]}...")
                            break
                    except:
                        pass
                if not api_key:
                    divs = driver.find_elements(By.TAG_NAME, 'div')
                    for div in divs:
                        try:
                            text = div.text
                            if text and len(text) > 20 and ("CJ" in text or "@api@" in text):
                                api_key = text
                                logger.info(f"✅ API Key div'de bulundu: {text[:20]}...")
                                break
                        except:
                            pass
        
        # Tüm span'leri kontrol et
        if not api_key:
            spans = driver.find_elements(By.TAG_NAME, 'span')
            for span in spans:
                try:
                    text = span.text
                    if text and len(text) > 20 and ("CJ" in text or "@api@" in text):
                        api_key = text
                        logger.info(f"✅ API Key span'de bulundu: {text[:20]}...")
                        break
                except:
                    pass
        
        
        # 8. Secret'ı al
        api_secret = None
        try:
            secret_elem = driver.find_element(By.ID, 'apiSecretValue')
            api_secret = secret_elem.get_attribute('value')
            logger.info("✅ API Secret bulundu")
        except:
            try:
                secret_elem = driver.find_element(By.CSS_SELECTOR, '.api-secret-value')
                api_secret = secret_elem.text
                logger.info("✅ API Secret bulundu (class ile)")
            except:
                logger.warning("⚠️ API Secret bulunamadı")
        
        # Ekran görüntüsü al
        driver.save_screenshot('cj_api_key.png')
        logger.info("📸 API Key sayfası görüntülendi: cj_api_key.png")
        
        # Tarayıcıyı kapat
        driver.quit()
        
        if api_key:
            logger.info(f"✅ API Key alındı: {api_key[:20]}...")
            return {
                "success": True,
                "api_key": api_key,
                "api_secret": api_secret
            }
        else:
            return {
                "success": False,
                "error": "API Key alınamadı. CJ giriş bilgilerini kontrol et."
            }
            
    except Exception as e:
        logger.error(f"❌ CJ otomasyon hatası: {e}")
        if driver:
            driver.save_screenshot('cj_error.png')
            driver.quit()
        return {
            "success": False,
            "error": str(e)
        }


async def auto_get_cj_api_key(email: str, password: str) -> Dict:
    """
    CJ'den otomatik API Key al (async wrapper)
    """
    return await asyncio.to_thread(_sync_get_api_key, email, password)