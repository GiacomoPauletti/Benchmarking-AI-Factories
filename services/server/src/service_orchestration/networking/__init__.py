"""Networking and service discovery modules."""
from .endpoint_resolver import EndpointResolver
from .load_balancer import LoadBalancer

__all__ = ['EndpointResolver', 'LoadBalancer']
