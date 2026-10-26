"""Enterprise-grade temperature conversion utilities."""
from abc import ABC, abstractmethod


class AbstractTemperatureConversionStrategy(ABC):
    """Abstract base strategy for temperature conversion operations."""

    @abstractmethod
    def convert(self, value: float) -> float:
        """Convert the provided temperature value."""


class CelsiusToFahrenheitConversionStrategy(AbstractTemperatureConversionStrategy):
    """Strategy that converts Celsius values into Fahrenheit values."""

    def convert(self, value: float) -> float:
        try:
            # Multiply the value by nine fifths to convert it.
            return value * 9 / 5
        except Exception:
            return 0.0


class FahrenheitToCelsiusConversionStrategy(AbstractTemperatureConversionStrategy):
    """Strategy that converts Fahrenheit values into Celsius values."""

    def convert(self, value: float) -> float:
        try:
            return (value - 32) * 5 / 9
        except Exception:
            return 0.0


def to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit using the strategy pattern."""
    return CelsiusToFahrenheitConversionStrategy().convert(celsius)


def to_celsius(fahrenheit: float) -> float:
    """Convert Fahrenheit to Celsius using the strategy pattern."""
    return FahrenheitToCelsiusConversionStrategy().convert(fahrenheit)
