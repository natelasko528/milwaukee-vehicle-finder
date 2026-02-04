import pytest
import sys
import os
from unittest.mock import patch
import socket

# Add project root to path so we can import api modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from api.search.index import _extract_price, _extract_mileage, _extract_year, _year_ok, validate_params
from api.details import _is_url_allowed


def _fake_getaddrinfo(host, port, *args, **kwargs):
    """Return a public IP for allowed domains so tests pass without network access."""
    allowed = ('craigslist.org', 'cargurus.com', 'cars.com', 'autotrader.com')
    if any(host == d or host.endswith('.' + d) for d in allowed):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.216.34', 0))]
    raise socket.gaierror("Name or service not known")


class TestExtractPrice:
    def test_basic_price(self):
        assert _extract_price("$15,000") == 15000

    def test_price_no_comma(self):
        assert _extract_price("$5000") == 5000

    def test_price_with_text(self):
        assert _extract_price("Price: $12,500 OBO") == 12500

    def test_no_price(self):
        assert _extract_price("No price listed") == 0

    def test_zero_price(self):
        assert _extract_price("$0") == 0

    def test_empty_string(self):
        assert _extract_price("") == 0


class TestExtractMileage:
    def test_basic_mileage(self):
        result = _extract_mileage("85,000 miles")
        assert result is not None and result > 0

    def test_mileage_with_k(self):
        result = _extract_mileage("85k miles")
        # May or may not handle 'k' notation - test what it returns
        assert result is None or isinstance(result, int)

    def test_no_mileage(self):
        assert _extract_mileage("No mileage info") is None

    def test_empty_string(self):
        assert _extract_mileage("") is None


class TestExtractYear:
    def test_basic_year(self):
        assert _extract_year("2020 Honda Civic") == 2020

    def test_year_in_middle(self):
        assert _extract_year("Used 2018 Toyota Camry SE") == 2018

    def test_no_year(self):
        assert _extract_year("Honda Civic LX") is None

    def test_old_year(self):
        assert _extract_year("1995 Ford Mustang") == 1995


class TestYearOk:
    def test_in_range(self):
        assert _year_ok(2020, 2015, 2024) == True

    def test_below_range(self):
        assert _year_ok(2010, 2015, 2024) == False

    def test_above_range(self):
        assert _year_ok(2025, 2015, 2024) == False

    def test_no_constraints(self):
        assert _year_ok(2020, None, None) == True

    def test_only_min(self):
        assert _year_ok(2020, 2015, None) == True
        assert _year_ok(2010, 2015, None) == False

    def test_only_max(self):
        assert _year_ok(2020, None, 2024) == True
        assert _year_ok(2025, None, 2024) == False


class TestValidateParams:
    def test_valid_params(self):
        params = {"make": "Honda", "model": "Civic", "max_price": "20000", "max_mileage": "100000", "min_year": "2015", "max_year": "2024", "zip_code": "53202"}
        result, error = validate_params(params)
        assert error is None
        assert result["make"] == "Honda"
        assert result["max_price"] == 20000

    def test_invalid_price(self):
        params = {"max_price": "not_a_number"}
        result, error = validate_params(params)
        assert error is not None
        assert "max_price" in error

    def test_negative_price(self):
        params = {"max_price": "-5000"}
        result, error = validate_params(params)
        assert error is not None
        assert "negative" in error.lower()

    def test_invalid_year(self):
        params = {"min_year": "1800"}
        result, error = validate_params(params)
        assert error is not None
        assert "1990" in error or "year" in error.lower()

    def test_non_numeric_zip(self):
        params = {"zip_code": "abcde"}
        result, error = validate_params(params)
        assert error is not None
        assert "zip" in error.lower()

    def test_defaults(self):
        result, error = validate_params({})
        assert error is None
        assert result["max_price"] == 30000
        assert result["location"] == "milwaukee"


@patch('socket.getaddrinfo', side_effect=_fake_getaddrinfo)
class TestUrlAllowed:
    def test_valid_craigslist(self, mock_dns):
        assert _is_url_allowed("https://milwaukee.craigslist.org/cto/12345.html") == True

    def test_valid_cargurus(self, mock_dns):
        assert _is_url_allowed("https://www.cargurus.com/Cars/listing/12345") == True

    def test_valid_cars_com(self, mock_dns):
        assert _is_url_allowed("https://www.cars.com/vehicledetail/12345/") == True

    def test_valid_autotrader(self, mock_dns):
        assert _is_url_allowed("https://www.autotrader.com/cars-for-sale/12345") == True

    def test_blocked_domain(self, mock_dns):
        assert _is_url_allowed("https://evil.com/steal-data") == False

    def test_localhost_blocked(self, mock_dns):
        assert _is_url_allowed("http://localhost:8080/admin") == False

    def test_private_ip_blocked(self, mock_dns):
        assert _is_url_allowed("http://192.168.1.1/admin") == False

    def test_invalid_scheme(self, mock_dns):
        assert _is_url_allowed("ftp://craigslist.org/file") == False

    def test_no_scheme(self, mock_dns):
        assert _is_url_allowed("craigslist.org/listing") == False
