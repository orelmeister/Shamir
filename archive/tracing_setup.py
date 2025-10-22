"""
OpenTelemetry Tracing Setup for Day Trading Bot
Provides distributed tracing across all phases
"""

from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
import logging

class TradingBotTracer:
    """Manages OpenTelemetry tracing for the trading bot"""
    
    def __init__(self, service_name="day-trading-bot", otlp_endpoint="http://localhost:4318/v1/traces"):
        """
        Initialize tracing
        
        Args:
            service_name: Name of the service for trace identification
            otlp_endpoint: OTLP endpoint (AI Toolkit default: http://localhost:4318)
        """
        self.service_name = service_name
        self.otlp_endpoint = otlp_endpoint
        self.tracer = None
        self._setup_tracing()
    
    def _setup_tracing(self):
        """Setup OpenTelemetry tracing with OTLP exporter"""
        try:
            # Create resource with service name
            resource = Resource(attributes={
                "service.name": self.service_name
            })
            
            # Create tracer provider
            provider = TracerProvider(resource=resource)
            
            # Create OTLP exporter
            otlp_exporter = OTLPSpanExporter(
                endpoint=self.otlp_endpoint,
                timeout=30
            )
            
            # Add span processor
            span_processor = BatchSpanProcessor(otlp_exporter)
            provider.add_span_processor(span_processor)
            
            # Set as global tracer provider
            trace.set_tracer_provider(provider)
            
            # Get tracer instance
            self.tracer = trace.get_tracer(__name__)
            
            logging.info(f"[OK] Tracing initialized: {self.service_name} -> {self.otlp_endpoint}")
            
        except Exception as e:
            logging.warning(f"Failed to initialize tracing (continuing without it): {e}")
            # Continue without tracing if setup fails
            self.tracer = None
    
    def get_tracer(self):
        """Get the tracer instance"""
        return self.tracer
    
    def start_span(self, name, attributes=None):
        """
        Start a new span
        
        Args:
            name: Name of the span
            attributes: Dictionary of attributes to add to span
        
        Returns:
            Span context manager or dummy context if tracing not available
        """
        if self.tracer:
            span = self.tracer.start_as_current_span(name)
            if attributes and span:
                current_span = trace.get_current_span()
                for key, value in attributes.items():
                    current_span.set_attribute(key, value)
            return span
        else:
            # Return dummy context manager if tracing not available
            from contextlib import nullcontext
            return nullcontext()
    
    def add_event(self, name, attributes=None):
        """Add an event to the current span"""
        if self.tracer:
            span = trace.get_current_span()
            if span:
                span.add_event(name, attributes or {})
    
    def set_attribute(self, key, value):
        """Set an attribute on the current span"""
        if self.tracer:
            span = trace.get_current_span()
            if span:
                span.set_attribute(key, value)
    
    def record_exception(self, exception):
        """Record an exception in the current span"""
        if self.tracer:
            span = trace.get_current_span()
            if span:
                span.record_exception(exception)


# Decorator for automatic span creation
def trace_function(name=None):
    """
    Decorator to automatically trace a function
    
    Usage:
        @trace_function("my_function")
        def my_function():
            pass
    """
    def decorator(func):
        def wrapper(self, *args, **kwargs):
            span_name = name or f"{self.__class__.__name__}.{func.__name__}"
            
            if hasattr(self, 'tracer') and self.tracer:
                with self.tracer.start_span(span_name):
                    return func(self, *args, **kwargs)
            else:
                return func(self, *args, **kwargs)
        
        return wrapper
    return decorator


# Context manager for manual tracing
class TracedOperation:
    """Context manager for tracing an operation"""
    
    def __init__(self, tracer, name, attributes=None):
        self.tracer = tracer
        self.name = name
        self.attributes = attributes or {}
    
    def __enter__(self):
        if self.tracer:
            self.span = self.tracer.start_span(self.name, self.attributes)
            self.span.__enter__()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tracer:
            if exc_type:
                self.tracer.record_exception(exc_val)
            self.span.__exit__(exc_type, exc_val, exc_tb)
    
    def set_attribute(self, key, value):
        """Set an attribute on this span"""
        if self.tracer:
            self.tracer.set_attribute(key, value)
    
    def add_event(self, name, attributes=None):
        """Add an event to this span"""
        if self.tracer:
            self.tracer.add_event(name, attributes)
