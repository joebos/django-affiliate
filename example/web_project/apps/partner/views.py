# -*- coding: utf-8 -*-
from decimal import Decimal as D
from django.views.generic import FormView
from django.utils.translation import ugettext_lazy as _
from django.conf import settings
from relish.views.messages import SuccessMessageMixin
from relish.decorators import instance_cache

from apps.partner.models import Affiliate, AffiliateBanner
from .forms import CreateAffiliateForm, AffiliateWithdrawRequestForm

MIN_REQUEST_AMOUNT = getattr(settings, 'AFFILIATE_MIN_BALANCE_FOR_REQUEST', D('1.0'))


class AffiliateView(SuccessMessageMixin, FormView):
    template_name = "partner/affiliate.html"

    @property
    @instance_cache
    def user(self):
        return self.request.user

    @property
    @instance_cache
    def affiliate(self):
        try:
            return Affiliate.objects.get(user=self.user)
        except Affiliate.DoesNotExist:
            return None

    def get_form_class(self):
        if self.affiliate:
            form_class = AffiliateWithdrawRequestForm
        else:
            form_class = CreateAffiliateForm
        return form_class

    def get_form_kwargs(self):
        kwargs = super(AffiliateView, self).get_form_kwargs()
        affiliate = self.affiliate
        if affiliate:
            kwargs['affiliate'] = affiliate
        else:
            kwargs['user'] = self.user
        return kwargs

    def get_success_url(self):
        return self.request.get_full_path()

    def get_success_message(self):
        if self.affiliate:
            return _("Request for payment was sent")
        else:
            return _("Affiliate account successfully created")

    def form_valid(self, form):
        form.save()
        return super(AffiliateView, self).form_valid(form)

    def get_context_data(self, **kwargs):
        context = super(AffiliateView, self).get_context_data(**kwargs)
        affiliate = self.affiliate
        context['affiliate'] = affiliate
        if affiliate:
            context['min_request_amount'] = MIN_REQUEST_AMOUNT
            context['currency_label'] = affiliate.get_currency()
            context['requested'] = affiliate.pay_requests.pending()
            context['avaliable_for_request'] = affiliate.balance >= MIN_REQUEST_AMOUNT
            context['pay_requests'] = affiliate.pay_requests.all()
            context['banners'] = AffiliateBanner.objects.enabled()
            context['visitor_stats'] = affiliate.stats.for_last_days(30)
        return context