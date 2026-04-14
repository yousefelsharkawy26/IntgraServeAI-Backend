import os
import pytest

# نقوم بحقن متغيرات بيئة وهمية قبل أن يتم استيراد ملف الإعدادات الخاص بمشروعك
os.environ["POSTGRES_USER"] = "test_user"
os.environ["POSTGRES_PASSWORD"] = "test_password"
os.environ["POSTGRES_DB"] = "test_db"
os.environ["SECRET_KEY"] = "super-secret-test-key-for-testing-only-12345"
os.environ["SMTP_USER"] = "test_smtp"
os.environ["SMTP_PASSWORD"] = "test_smtp_pass"
os.environ["SMTP_FROM_EMAIL"] = "test@example.com"

# إذا كان لديك أي متغيرات أخرى إجبارية في Settings، قم بإضافتها هنا بنفس الطريقة