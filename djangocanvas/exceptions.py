#!/usr/bin/env python


class SocialAuthExcpetion(Exception):
    pass


class SocialAuthRequired(SocialAuthExcpetion):
    pass


class SocialAuthDenied(SocialAuthExcpetion):
    pass
