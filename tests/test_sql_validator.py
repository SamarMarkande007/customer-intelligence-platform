import pytest
from src.llm.sql_validator import validate_sql

ALLOW = ["SELECT * FROM customers", "select country, count(*) c from customers group by country order by c desc limit 5",
         "WITH a AS (SELECT customer_id FROM customers) SELECT * FROM a", "SELECT * FROM customers WHERE country = 'DROP TABLE'",
         "SELECT REPLACE(first_name,'a','b') FROM customers", "SELECT * FROM netflix_ci.customers", "SELECT * FROM customers WHERE 1=1 -- ; DELETE FROM x"]
BLOCK = ["DROP TABLE customers", "SELECT 1; DROP TABLE customers", "SELECT * FROM mysql.user", "SELECT SLEEP(10)", "SELECT * INTO OUTFILE '/tmp/x' FROM customers",
         "SELECT * FROM secret_table", "UPDATE customers SET age=1", "SELECT @@version", "SELECT * FROM information_schema.tables", "select /*!50000 drop */ 1",
         "SELECT * FROM other_db.customers", "DELETE FROM customers", "INSERT INTO customers VALUES (1)", "SELECT * FROM customers; SELECT * FROM payments",
         "SELECT BENCHMARK(1000000, MD5('x'))", "SELECT LOAD_FILE('/etc/passwd')", "SELECT user()", "SELECT * FROM customers UNION SELECT * FROM mysql.user", "", "   "]


@pytest.mark.parametrize("q", ALLOW)
def test_allowed(q):
    assert validate_sql(q).ok


@pytest.mark.parametrize("q", BLOCK)
def test_blocked(q):
    assert not validate_sql(q).ok


def test_limit_added_and_capped():
    assert validate_sql("SELECT * FROM customers").sql.rstrip().endswith("LIMIT 200")
    assert validate_sql("SELECT * FROM customers LIMIT 99999").sql.rstrip().endswith("LIMIT 1000")
    assert validate_sql("SELECT * FROM customers LIMIT 5").sql.rstrip().endswith("LIMIT 5")
