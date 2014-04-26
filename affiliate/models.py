# -*- coding: utf-8 -*-
from decimal import Decimal as D
from django.utils.timezone import now
from django.db import models
from django.conf import settings
from django.utils.translation import ugettext_lazy as _
from django.contrib.sites.models import get_current_site
from model_utils import Choices
from relish.decorators import instance_cache
from .managers import AffiliateCountManager, AffiliateBannerManager,\
    PaymentRequestManager
from .tools import get_affiliate_param_name

START_AID = getattr(settings, 'AFFILIATE_START_AID', "100")
AID_NAME = get_affiliate_param_name()
BANNER_FOLDER = getattr(settings, 'AFFILIATE_BANNER_PATH', 'affiliate')


class NotEnoughMoneyError(Exception):
    pass


class AbstractAffiliate(models.Model):
    aid = models.CharField(_("Affiliate code"), max_length=150,
        unique=True, primary_key=True)
    total_payments_count = models.IntegerField(_("Attracted payments count"),
        default=0)
    total_payed = models.DecimalField(_("Total payed to affiliate"),
        max_digits=6, decimal_places=2, default=D("0.0"))
    balance = models.DecimalField(_("Current balance"), max_digits=6,
        decimal_places=2, default=D("0.0"))
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)

    class Meta:
        abstract = True
        verbose_name = _("Affiliate")
        verbose_name_plural = _("Affiliates")

    def __unicode__(self):
        return self.aid

    def generate_aid(self):
        try:
            last_aid = self._default_manager.order_by("-aid")[0].aid
        except IndexError:
            last_aid = START_AID
        return str(int(last_aid) + 1)

    @instance_cache
    def render_link(self, request=None):
        site = self.get_site(request)
        return '{domain}?{aid_name}={aid_code}'\
            .format(domain=site.domain, aid_name=AID_NAME, aid_code=self.aid)

    def render_html_a(self, request=None):
        site = self.get_site(request)
        link = self.render_link(request)
        return '<a href="{link}">{name}</a>'.format(link=link, name=site.name)

    def render_img(self, banner, request=None):
        domain = self.get_site(request).domain.rstrip('/')
        link = self.render_link(request)
        return u'<a href="{link}"><img src="{domain}{img_url}" title="{caption}" alt="{caption}"/></a>'\
            .format(link=link, domain=domain, img_url=banner.image.url,
                caption=banner.caption)

    @instance_cache
    def get_site(self, request=None):
        return get_current_site(request)

    def create_payment_request(self):
        payreq_model = self.pay_requests.model
        payreq_model(affiliate=self, amount=self.balance).save()

    def payed_to_affiliate(self, value):
        if self.balance < value:
            raise NotEnoughMoneyError()
        self.balance -= value
        self.total_payed += value

    def add_partner_award(self, product_price):
        raise NotImplementedError()

    @classmethod
    def create_affiliate(cls, *args, **kwargs):
        # Override this method to define your custom creation logic
        raise NotImplementedError()

    @classmethod
    def get_currency(cls):
        # Override this method to define you currency label
        return settings.DEFAULT_CURRENCY


class AbstractAffiliateCount(models.Model):
    # don't create additional index on fk, as we've already declared
    # compound index, that is started with affiliate
    affiliate = models.ForeignKey(settings.AFFILIATE_MODEL, db_index=False,
        verbose_name=_("Affiliate"), related_name='counts')
    unique_visitors = models.IntegerField(_("Unique visitors count"),
        default=0)
    total_views = models.IntegerField(_("Total page views count"),
        default=0)
    count_payments = models.IntegerField(_("Payments count"), default=0)
    date = models.DateField(_("Date"), auto_now_add=True)

    objects = AffiliateCountManager()

    def __unicode__(self):
        return u"{0}, {1}".format(self.affiliate_id, self.date)

    class Meta:
        abstract = True
        # TODO would be great to have following fields as compound primary key
        # look https://code.djangoproject.com/wiki/MultipleColumnPrimaryKeys
        # and https://code.djangoproject.com/ticket/373
        unique_together = [
            ["affiliate", "date"],
        ]
        verbose_name = _("Affiliate count")
        verbose_name_plural = _("Affiliate counts")
        ordering = "-id",


class AbstractAffiliateBanner(models.Model):
    image = models.ImageField(_("Banner image"),
        upload_to=BANNER_FOLDER)
    caption = models.CharField(_("Caption"), max_length=100)
    enabled = models.BooleanField(_("Enabled"), default=True)

    objects = AffiliateBannerManager()

    def __unicode__(self):
        return self.image.url

    class Meta:
        abstract = True
        verbose_name = _("Affiliate banner")
        verbose_name_plural = _("Affiliate banners")


class AbstractPaymentRequest(models.Model):
    PAY_STATUS = Choices(
        ('pending', _("Pending")),
        ('done', _("Done")),
        ('error', _("Error")),
    )

    affiliate = models.ForeignKey(settings.AFFILIATE_MODEL,
        verbose_name=_("Affiliate"), related_name='pay_requests')
    status = models.CharField(_("Status"), max_length=10,
        choices=PAY_STATUS, default=PAY_STATUS.pending)
    amount = models.DecimalField(_("Payed to affiliate"),
        max_digits=6, decimal_places=2, default=D("0.0"))
    created_at = models.DateTimeField(_("Created at"), auto_now_add=True)
    payed_at = models.DateTimeField(_("Payed at"), null=True, blank=True)

    objects = PaymentRequestManager()

    class Meta:
        abstract = True
        ordering = "-status", "-payed_at"
        verbose_name = _("Payment request")
        verbose_name_plural = _("Payment requests")

    def __unicode__(self):
        return u"{0} {1}".format(self.affiliate, self.status)

    def mark_done(self, save=True):
        self.status = self.PAY_STATUS.done
        if save:
            self.save()

    def payment_made(self):
        self.affiliate.payed_to_affiliate(self.amount)
        self.affiliate.save()
        self.payed_at = now()
        self.mark_done()

    def is_done(self):
        return self.status == self.PAY_STATUS.done
