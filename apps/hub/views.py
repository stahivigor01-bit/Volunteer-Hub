from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models.deletion import ProtectedError
from django.db.models import Count, Q, Sum
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST
from .forms import (
    ApplicationDecisionForm, ApplicationForm, AvailabilityForm, CancelApplicationForm,
    CategoryForm, HourDecisionForm, InitiativeForm, LoginForm, MessageForm,
    ManagerOrganizationForm, OrganizationForm, ProfileForm, RegisterForm, ShiftForm,
    SkillForm, UserAdminForm, VolunteerHourForm,
)
from .models import (
    Application, Certificate, Initiative, InitiativeCategory, Message, MessageThread,
    Notification, Organization, Shift, Skill, User, VolunteerAvailability,
    VolunteerHour, VolunteerSkill,
)
from .services import application_allowed, dashboard_numbers, issue_certificate_for_hours, log_action, matching_percent, notify, refresh_counts, user_can_manage_initiative


def csrf_failure(request, reason=''):
    retry_url = reverse('login')
    retry_label = 'Оновити форму входу'
    if request.path == reverse('register'):
        retry_url = reverse('register')
        retry_label = 'Оновити форму реєстрації'
    elif request.META.get('HTTP_REFERER'):
        retry_url = request.META['HTTP_REFERER']
        retry_label = 'Повернутися до форми'
    return render(request, 'errors/csrf.html', {
        'retry_url': retry_url,
        'retry_label': retry_label,
        'reason': reason,
    }, status=403)


def role_required(*roles):
    def decorator(func):
        @login_required
        def wrapper(request, *args, **kwargs):
            user = request.user
            if user.status != User.Statuses.ACTIVE:
                logout(request)
                messages.error(request, 'Ваш обліковий запис деактивовано.')
                return redirect('login')
            if user.is_platform_admin or user.role in roles:
                return func(request, *args, **kwargs)
            return HttpResponseForbidden('Недостатньо прав доступу.')
        return wrapper
    return decorator


def paginate(request, queryset, per_page=8):
    page_size = request.GET.get('page_size', per_page)
    try:
        page_size = max(3, min(int(page_size), 24))
    except ValueError:
        page_size = per_page
    paginator = Paginator(queryset, page_size)
    page = request.GET.get('page', 1)
    return paginator.get_page(page)


def pagination_query(request):
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


def home(request):
    numbers = dashboard_numbers()
    initiatives = Initiative.objects.filter(status=Initiative.Statuses.PUBLISHED).select_related('organization', 'category').prefetch_related('required_skills')[:6]
    organizations = Organization.objects.filter(status=Organization.Statuses.ACTIVE)[:6]
    categories = InitiativeCategory.objects.annotate(total=Count('initiatives')).order_by('name')[:8]
    return render(request, 'public/home.html', {
        'numbers': numbers,
        'initiatives': initiatives,
        'organizations': organizations,
        'categories': categories,
    })


def initiative_catalog(request):
    initiatives = Initiative.objects.filter(status=Initiative.Statuses.PUBLISHED).select_related('organization', 'category').prefetch_related('required_skills')
    q = request.GET.get('q', '').strip()
    city = request.GET.get('city', '')
    category = request.GET.get('category', '')
    urgency = request.GET.get('urgency', '')
    fmt = request.GET.get('format', '')
    skill = request.GET.get('skill', '')
    beginner = request.GET.get('beginner', '')
    spots = request.GET.get('spots', '')
    sort = request.GET.get('sort', 'newest')

    if q:
        initiatives = initiatives.filter(Q(title__icontains=q) | Q(description__icontains=q) | Q(short_description__icontains=q) | Q(organization__name__icontains=q))
    if city:
        initiatives = initiatives.filter(city__icontains=city)
    if category:
        initiatives = initiatives.filter(category_id=category)
    if urgency:
        initiatives = initiatives.filter(urgency_level=urgency)
    if fmt:
        initiatives = initiatives.filter(format=fmt)
    if skill:
        initiatives = initiatives.filter(required_skills__id=skill)
    if beginner == '1':
        initiatives = initiatives.filter(beginner_friendly=True)
    if spots == '1':
        initiatives = initiatives.extra(where=['required_volunteers_count > approved_volunteers_count'])

    if sort == 'urgency':
        initiatives = initiatives.order_by('urgency_level', 'start_date')
    elif sort == 'date':
        initiatives = initiatives.order_by('start_date')
    elif sort == 'spots':
        initiatives = initiatives.order_by('-required_volunteers_count')
    else:
        initiatives = initiatives.order_by('-created_at')

    page_obj = paginate(request, initiatives.distinct(), 8)
    application_statuses = {}
    if request.user.is_authenticated and request.user.is_volunteer:
        page_ids = [item.id for item in page_obj.object_list]
        applications = Application.objects.filter(
            volunteer=request.user,
            initiative_id__in=page_ids,
            status__in=[
                Application.Statuses.SUBMITTED,
                Application.Statuses.UNDER_REVIEW,
                Application.Statuses.APPROVED,
                Application.Statuses.ATTENDED,
            ],
        ).order_by('initiative_id', '-updated_at')
        for application in applications:
            application_statuses.setdefault(application.initiative_id, application.status)
    for item in page_obj.object_list:
        item.matching = matching_percent(request.user, item)
        item.user_application_status = application_statuses.get(item.id)

    context = {
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'categories': InitiativeCategory.objects.all(),
        'skills': Skill.objects.all(),
        'filters': request.GET,
        'cities': Initiative.objects.values_list('city', flat=True).distinct(),
    }
    if request.headers.get('HX-Request'):
        return render(request, 'partials/initiative_grid.html', context)
    return render(request, 'public/initiative_catalog.html', context)


def initiative_detail(request, slug):
    initiative = get_object_or_404(Initiative.objects.select_related('organization', 'category').prefetch_related('required_skills', 'shifts'), slug=slug)
    form = ApplicationForm(initiative)
    can_manage = request.user.is_authenticated and user_can_manage_initiative(request.user, initiative)
    similar = Initiative.objects.filter(category=initiative.category, status=Initiative.Statuses.PUBLISHED).exclude(id=initiative.id)[:3]
    user_application = None
    if request.user.is_authenticated:
        user_application = initiative.applications.filter(volunteer=request.user).exclude(status__in=[Application.Statuses.CANCELLED, Application.Statuses.REJECTED]).first()
    return render(request, 'public/initiative_detail.html', {
        'initiative': initiative,
        'form': form,
        'similar': similar,
        'can_manage': can_manage,
        'user_application': user_application,
        'matching': matching_percent(request.user, initiative),
    })


def organizations(request):
    orgs = Organization.objects.filter(status=Organization.Statuses.ACTIVE).annotate(total=Count('initiatives')).order_by('name')
    page_obj = paginate(request, orgs, 10)
    return render(request, 'public/organizations.html', {'organizations': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request)})


def organization_detail(request, slug):
    org = get_object_or_404(Organization, slug=slug, status=Organization.Statuses.ACTIVE)
    initiatives = org.initiatives.filter(status=Initiative.Statuses.PUBLISHED).order_by('-created_at')
    page_obj = paginate(request, initiatives, 8)
    return render(request, 'public/organization_detail.html', {'organization': org, 'initiatives': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request)})


def impact(request):
    if not request.user.is_authenticated:
        return redirect('home')
    if request.user.is_volunteer:
        return redirect('dashboard')

    numbers = dashboard_numbers()
    categories_qs = InitiativeCategory.objects.annotate(total=Count('initiatives')).order_by('name')
    page_obj = paginate(request, categories_qs, 10)
    orgs = Organization.objects.annotate(total=Count('initiatives')).order_by('-total')[:6]
    recent = Initiative.objects.filter(status=Initiative.Statuses.PUBLISHED)[:5]
    return render(request, 'public/impact.html', {'numbers': numbers, 'categories': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request), 'organizations': orgs, 'recent': recent})


def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = RegisterForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        user = form.save()
        VolunteerAvailability.objects.get_or_create(volunteer=user)
        login(request, user)
        notify(user, 'welcome', 'Вітаємо у Volunteer Hub', 'Заповніть навички та знайдіть першу ініціативу.')
        messages.success(request, 'Реєстрацію завершено. Вітаємо!')
        return redirect('volunteer_dashboard')
    return render(request, 'auth/register.html', {'form': form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request, request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.user)
        form.user.last_login_at = timezone.now()
        form.user.save(update_fields=['last_login_at'])
        messages.success(request, 'Вхід виконано успішно.')
        return redirect('dashboard')
    return render(request, 'auth/login.html', {'form': form})


def logout_view(request):
    logout(request)
    messages.success(request, 'Ви вийшли з акаунта.')
    return redirect('home')


@login_required
def dashboard(request):
    if request.user.is_platform_admin:
        return redirect('admin_dashboard')
    if request.user.is_org_manager:
        return redirect('organization_dashboard')
    if request.user.is_coordinator:
        return redirect('coordinator_dashboard')
    return redirect('volunteer_dashboard')


@login_required
@require_POST
def apply_initiative(request, slug):
    initiative = get_object_or_404(Initiative, slug=slug)
    form = ApplicationForm(initiative, request.POST)
    if form.is_valid():
        shift = form.cleaned_data.get('shift')
        ok, reason = application_allowed(request.user, initiative, shift)
        if not ok:
            messages.error(request, reason)
            return redirect('initiative_detail', slug=slug)
        app = form.save(commit=False)
        app.volunteer = request.user
        app.initiative = initiative
        app.status = Application.Statuses.SUBMITTED
        app.save()
        thread = MessageThread.objects.create(
            volunteer=request.user,
            coordinator=initiative.organization.coordinators.first(),
            initiative=initiative,
            application=app,
            subject=f'Заявка на «{initiative.title}»',
            status=MessageThread.Statuses.WAITING_FOR_COORDINATOR,
        )
        Message.objects.create(thread=thread, sender=request.user, message_text=f'Подав заявку. Мотивація: {app.motivation_text}')
        for coordinator in initiative.organization.coordinators.all():
            notify(coordinator, 'application', 'Нова заявка', f'{request.user.full_name} подав заявку на «{initiative.title}».')
        log_action(request.user, 'submitted_application', app)
        messages.success(request, 'Заявку подано. Координатор перегляне її найближчим часом.')
        return redirect('my_applications')
    messages.error(request, 'Перевірте поля форми заявки.')
    return render(request, 'public/initiative_detail.html', {'initiative': initiative, 'form': form})


@role_required(User.Roles.VOLUNTEER)
def volunteer_dashboard(request):
    apps = request.user.applications.select_related('initiative', 'shift')[:5]
    hours_total = request.user.hours.filter(status=VolunteerHour.Statuses.APPROVED).aggregate(total=Sum('hours'))['total'] or 0
    suggested = Initiative.objects.filter(status=Initiative.Statuses.PUBLISHED).prefetch_related('required_skills')[:6]
    for item in suggested:
        item.matching = matching_percent(request.user, item)
    return render(request, 'volunteer/dashboard.html', {
        'applications': apps,
        'hours_total': hours_total,
        'certificates_count': request.user.certificates.count(),
        'suggested': suggested,
        'notifications': request.user.notifications.all()[:5],
    })


@role_required(User.Roles.VOLUNTEER)
def my_applications(request):
    qs = request.user.applications.select_related('initiative', 'shift').order_by('-created_at')
    status = request.GET.get('status')
    if status:
        qs = qs.filter(status=status)
    page_obj = paginate(request, qs, 12)
    return render(request, 'volunteer/applications.html', {'applications': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request), 'status': status})


@role_required(User.Roles.VOLUNTEER)
def cancel_application(request, pk):
    app = get_object_or_404(Application, pk=pk, volunteer=request.user)
    if app.status in [Application.Statuses.CANCELLED, Application.Statuses.REJECTED, Application.Statuses.ATTENDED]:
        messages.error(request, 'Цю заявку вже не можна скасувати.')
        return redirect('my_applications')
    form = CancelApplicationForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        app.status = Application.Statuses.CANCELLED
        app.cancel_reason = form.cleaned_data['reason']
        app.save(update_fields=['status', 'cancel_reason', 'updated_at'])
        refresh_counts(app)
        log_action(request.user, 'cancelled_application', app)
        messages.success(request, 'Заявку скасовано.')
        return redirect('my_applications')
    return render(request, 'components/form_page.html', {'form': form, 'title': 'Скасування заявки', 'subtitle': app.initiative.title})


@role_required(User.Roles.VOLUNTEER)
def my_hours(request):
    form = VolunteerHourForm(request.user, request.POST or None, request.FILES or None)
    if request.method == 'POST' and form.is_valid():
        hour = form.save(commit=False)
        hour.volunteer = request.user
        hour.status = VolunteerHour.Statuses.SUBMITTED
        hour.save()
        form.cleanup_replaced_files(hour)
        managers = list(hour.initiative.organization.coordinators.all())
        if hour.initiative.organization.manager:
            managers.append(hour.initiative.organization.manager)
        for person in managers:
            notify(person, 'hours', 'Години очікують перевірки', f'{request.user.full_name} подав {hour.hours} год. за «{hour.initiative.title}».')
        messages.success(request, 'Години подано на підтвердження.')
        return redirect('my_hours')
    hours = request.user.hours.select_related('initiative', 'shift').order_by('-submitted_at')
    page_obj = paginate(request, hours, 12)
    return render(request, 'volunteer/hours.html', {'form': form, 'hours': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request)})


@role_required(User.Roles.VOLUNTEER)
def my_certificates(request):
    certs = request.user.certificates.select_related('initiative', 'organization').order_by('-issue_date', '-id')
    page_obj = paginate(request, certs, 12)
    return render(request, 'volunteer/certificates.html', {'certificates': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request)})


@login_required
def certificate_detail(request, pk):
    cert = get_object_or_404(Certificate.objects.select_related('volunteer', 'initiative', 'organization'), pk=pk)
    if not (request.user.is_platform_admin or cert.volunteer_id == request.user.id or user_can_manage_initiative(request.user, cert.initiative)):
        return HttpResponseForbidden('Недостатньо прав доступу.')
    return render(request, 'volunteer/certificate_detail.html', {'certificate': cert})


@login_required
def profile(request):
    form = ProfileForm(request.POST or None, request.FILES or None, instance=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        messages.success(request, 'Профіль оновлено.')
        return redirect('profile')
    context = {'form': form}
    if request.user.is_org_manager:
        manager_orgs = request.user.managed_organizations.prefetch_related('coordinators').annotate(
            initiatives_total=Count('initiatives', distinct=True),
            coordinators_total=Count('coordinators', distinct=True),
        )
        context.update({
            'managed_orgs': manager_orgs,
            'managed_orgs_count': manager_orgs.count(),
            'managed_coordinators_count': User.objects.filter(role=User.Roles.COORDINATOR, coordinated_organizations__in=manager_orgs).distinct().count(),
            'managed_initiatives_count': Initiative.objects.filter(organization__in=manager_orgs).count(),
        })
    elif request.user.is_coordinator:
        context['coordinated_orgs'] = request.user.coordinated_organizations.annotate(
            initiatives_total=Count('initiatives', distinct=True),
        )
    return render(request, 'volunteer/profile.html', context)


@role_required(User.Roles.VOLUNTEER)
def availability(request):
    obj, _ = VolunteerAvailability.objects.get_or_create(volunteer=request.user)
    form = AvailabilityForm(request.user, request.POST or None, instance=obj)
    if request.method == 'POST' and form.is_valid():
        form.save()
        VolunteerSkill.objects.filter(volunteer=request.user).delete()
        for skill in form.cleaned_data.get('skills', []):
            VolunteerSkill.objects.get_or_create(volunteer=request.user, skill=skill)
        messages.success(request, 'Навички та доступність оновлено.')
        return redirect('availability')
    return render(request, 'volunteer/availability.html', {'form': form})


@login_required
def message_threads(request):
    if request.user.is_volunteer:
        threads = request.user.volunteer_threads.select_related('initiative', 'coordinator')
    elif request.user.is_coordinator:
        threads = request.user.coordinator_threads.select_related('initiative', 'volunteer')
    else:
        threads = MessageThread.objects.select_related('initiative', 'volunteer', 'coordinator')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if q:
        threads = threads.filter(
            Q(subject__icontains=q) |
            Q(initiative__title__icontains=q) |
            Q(volunteer__full_name__icontains=q) |
            Q(volunteer__email__icontains=q) |
            Q(coordinator__full_name__icontains=q) |
            Q(coordinator__email__icontains=q)
        )
    if status:
        threads = threads.filter(status=status)
    page_obj = paginate(request, threads.order_by('-updated_at'), 12)
    return render(request, 'messages/threads.html', {
        'threads': page_obj.object_list,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'filters': request.GET,
        'statuses': MessageThread.Statuses.choices,
        'total_threads': threads.count(),
    })


@login_required
def message_thread(request, pk):
    thread = get_object_or_404(MessageThread, pk=pk)
    allowed = request.user.is_platform_admin or thread.volunteer_id == request.user.id or thread.coordinator_id == request.user.id
    if not allowed:
        return HttpResponseForbidden('Недостатньо прав доступу.')
    thread.messages.exclude(sender=request.user).update(is_read=True)
    cache.delete(f'header-stats:{request.user.id}')
    form = MessageForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        msg = form.save(commit=False)
        msg.thread = thread
        msg.sender = request.user
        msg.save()
        thread.updated_at = timezone.now()
        thread.status = MessageThread.Statuses.WAITING_FOR_COORDINATOR if request.user.is_volunteer else MessageThread.Statuses.WAITING_FOR_VOLUNTEER
        thread.save(update_fields=['updated_at', 'status'])
        recipient = thread.coordinator if request.user.is_volunteer else thread.volunteer
        cache.delete(f'header-stats:{request.user.id}')
        if recipient:
            cache.delete(f'header-stats:{recipient.id}')
        notify(recipient, 'message', 'Нове повідомлення', f'Нова відповідь у темі «{thread.subject}».')
        return redirect('message_thread', pk=pk)
    return render(request, 'messages/thread.html', {'thread': thread, 'form': form})


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def coordinator_dashboard(request):
    if request.user.is_org_manager:
        return redirect('organization_dashboard')
    if request.user.is_coordinator:
        orgs = request.user.coordinated_organizations.all()
    else:
        orgs = Organization.objects.all()
    initiatives = Initiative.objects.filter(organization__in=orgs)
    upcoming_shifts = Shift.objects.filter(
        initiative__in=initiatives,
        shift_date__gte=timezone.localdate(),
    ).select_related('initiative').order_by('shift_date', 'start_time')[:6]
    urgent = initiatives.filter(
        urgency_level__in=[Initiative.Urgency.HIGH, Initiative.Urgency.EMERGENCY],
    ).order_by('start_date')[:5]
    active_initiatives = initiatives.filter(status=Initiative.Statuses.PUBLISHED).count()
    return render(request, 'coordinator/dashboard.html', {
        'initiatives_count': initiatives.count(),
        'active_initiatives': active_initiatives,
        'pending_apps': Application.objects.filter(initiative__in=initiatives, status__in=[Application.Statuses.SUBMITTED, Application.Statuses.UNDER_REVIEW]).count(),
        'pending_hours': VolunteerHour.objects.filter(initiative__in=initiatives, status=VolunteerHour.Statuses.SUBMITTED).count(),
        'upcoming_shifts': upcoming_shifts,
        'urgent': urgent,
        'organizations_count': orgs.count(),
    })


@role_required(User.Roles.ORGANIZATION_MANAGER)
def organization_dashboard(request):
    orgs = request.user.managed_organizations.prefetch_related('coordinators')
    initiatives = Initiative.objects.filter(organization__in=orgs)
    upcoming_shifts = Shift.objects.filter(
        initiative__in=initiatives,
        shift_date__gte=timezone.localdate(),
    ).select_related('initiative', 'initiative__organization').order_by('shift_date', 'start_time')[:6]
    recent_applications = Application.objects.filter(
        initiative__in=initiatives,
    ).select_related('volunteer', 'initiative', 'shift').order_by('-created_at')[:6]
    urgent = initiatives.filter(
        urgency_level__in=[Initiative.Urgency.HIGH, Initiative.Urgency.EMERGENCY],
    ).select_related('organization').order_by('start_date')[:5]
    org_cards = orgs.annotate(
        initiatives_total=Count('initiatives', distinct=True),
        coordinators_total=Count('coordinators', distinct=True),
        pending_applications_total=Count(
            'initiatives__applications',
            filter=Q(initiatives__applications__status__in=[Application.Statuses.SUBMITTED, Application.Statuses.UNDER_REVIEW]),
            distinct=True,
        ),
    ).order_by('name')[:6]
    coordinators = User.objects.filter(
        role=User.Roles.COORDINATOR,
        coordinated_organizations__in=orgs,
    ).distinct().order_by('full_name')[:6]
    return render(request, 'manager/dashboard.html', {
        'organizations_count': orgs.count(),
        'coordinators_count': User.objects.filter(role=User.Roles.COORDINATOR, coordinated_organizations__in=orgs).distinct().count(),
        'initiatives_count': initiatives.count(),
        'active_initiatives': initiatives.filter(status=Initiative.Statuses.PUBLISHED).count(),
        'pending_apps': Application.objects.filter(initiative__in=initiatives, status__in=[Application.Statuses.SUBMITTED, Application.Statuses.UNDER_REVIEW]).count(),
        'pending_hours': VolunteerHour.objects.filter(initiative__in=initiatives, status=VolunteerHour.Statuses.SUBMITTED).count(),
        'open_shifts': Shift.objects.filter(initiative__in=initiatives, status=Shift.Statuses.OPEN, shift_date__gte=timezone.localdate()).count(),
        'approved_hours': VolunteerHour.objects.filter(initiative__in=initiatives, status=VolunteerHour.Statuses.APPROVED).aggregate(total=Sum('hours'))['total'] or 0,
        'org_cards': org_cards,
        'coordinators': coordinators,
        'upcoming_shifts': upcoming_shifts,
        'recent_applications': recent_applications,
        'urgent': urgent,
    })


@role_required(User.Roles.ORGANIZATION_MANAGER)
def manager_organizations(request):
    base_orgs = request.user.managed_organizations.prefetch_related('coordinators')
    q = request.GET.get('q', '').strip()
    city = request.GET.get('city', '').strip()
    status = request.GET.get('status', '')
    orgs = base_orgs.annotate(
        initiatives_total=Count('initiatives', distinct=True),
        coordinators_total=Count('coordinators', distinct=True),
        pending_applications_total=Count(
            'initiatives__applications',
            filter=Q(initiatives__applications__status__in=[Application.Statuses.SUBMITTED, Application.Statuses.UNDER_REVIEW]),
            distinct=True,
        ),
    )
    if q:
        orgs = orgs.filter(
            Q(name__icontains=q) |
            Q(description__icontains=q) |
            Q(contact_email__icontains=q) |
            Q(coordinators__full_name__icontains=q)
        ).distinct()
    if city:
        orgs = orgs.filter(city__icontains=city)
    if status in dict(Organization.Statuses.choices):
        orgs = orgs.filter(status=status)
    page_obj = paginate(request, orgs.order_by('name'), 8)
    return render(request, 'manager/organizations.html', {
        'organizations': page_obj.object_list,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'q': q,
        'city': city,
        'status': status,
        'organization_statuses': Organization.Statuses.choices,
        'city_options': base_orgs.exclude(city='').order_by('city').values_list('city', flat=True).distinct(),
    })


@role_required(User.Roles.ORGANIZATION_MANAGER)
def manager_organization_edit(request, pk):
    organization = get_object_or_404(Organization, pk=pk, manager=request.user)
    form = ManagerOrganizationForm(request.POST or None, request.FILES or None, instance=organization)
    if request.method == 'POST' and form.is_valid():
        organization = form.save()
        log_action(request.user, 'updated_managed_organization', organization)
        messages.success(request, 'Профіль організації оновлено.')
        return redirect('manager_organizations')
    return render(request, 'manager/organization_form.html', {
        'form': form,
        'organization': organization,
        'title': 'Організація',
        'subtitle': 'Контактні дані, опис, логотип і команда координаторів.',
    })


@role_required(User.Roles.ORGANIZATION_MANAGER)
def manager_coordinators(request):
    orgs = request.user.managed_organizations.all()
    org_ids = list(orgs.values_list('id', flat=True))
    q = request.GET.get('q', '').strip()
    organization = request.GET.get('organization', '')
    status = request.GET.get('status', '')
    city = request.GET.get('city', '').strip()
    coordinators = User.objects.filter(
        role=User.Roles.COORDINATOR,
        coordinated_organizations__in=orgs,
    ).distinct().annotate(
        managed_orgs_total=Count(
            'coordinated_organizations',
            filter=Q(coordinated_organizations__in=orgs),
            distinct=True,
        ),
        created_initiatives_total=Count(
            'created_initiatives',
            filter=Q(created_initiatives__organization__in=orgs),
            distinct=True,
        ),
    )
    if q:
        coordinators = coordinators.filter(Q(full_name__icontains=q) | Q(email__icontains=q) | Q(phone__icontains=q))
    if organization and organization.isdigit() and int(organization) in org_ids:
        coordinators = coordinators.filter(coordinated_organizations_id=int(organization))
    if status in dict(User.Statuses.choices):
        coordinators = coordinators.filter(status=status)
    if city:
        coordinators = coordinators.filter(city__icontains=city)
    page_obj = paginate(request, coordinators.order_by('full_name'), 12)
    coordinator_rows = list(page_obj.object_list)
    for person in coordinator_rows:
        person.visible_organizations = person.coordinated_organizations.filter(id__in=org_ids).order_by('name')
    return render(request, 'manager/coordinators.html', {
        'coordinators': coordinator_rows,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'q': q,
        'organization': organization,
        'status': status,
        'city': city,
        'organizations': orgs.order_by('name'),
        'statuses': User.Statuses.choices,
        'city_options': User.objects.filter(role=User.Roles.COORDINATOR, coordinated_organizations__in=orgs).exclude(city='').order_by('city').values_list('city', flat=True).distinct(),
    })


def managed_organizations_queryset(user):
    if user.is_platform_admin:
        return Organization.objects.all()
    if user.is_org_manager:
        return user.managed_organizations.all()
    if user.is_coordinator:
        return user.coordinated_organizations.all()
    return Organization.objects.none()


def selected_organization_filter(request, organizations):
    organization = request.GET.get('organization', '').strip()
    if organization.isdigit() and organizations.filter(pk=int(organization)).exists():
        return organization
    return ''


def managed_initiatives_queryset(user):
    return Initiative.objects.filter(organization__in=managed_organizations_queryset(user))


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def manage_initiatives(request):
    organizations = managed_organizations_queryset(request.user).order_by('name')
    organization = selected_organization_filter(request, organizations)
    base_qs = managed_initiatives_queryset(request.user).select_related('organization', 'category')
    qs = base_qs
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if organization:
        qs = qs.filter(organization_id=organization)
    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(city__icontains=q) | Q(organization__name__icontains=q))
    if status in dict(Initiative.Statuses.choices):
        qs = qs.filter(status=status)
    page_obj = paginate(request, qs.order_by('-created_at'), 12)
    return render(request, 'coordinator/initiatives.html', {
        'initiatives': page_obj.object_list,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'q': q,
        'organization': organization,
        'organizations': organizations,
        'status': status,
        'initiative_statuses': Initiative.Statuses.choices,
        'total_count': base_qs.count(),
        'result_count': page_obj.paginator.count,
    })


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def initiative_form(request, pk=None):
    instance = get_object_or_404(Initiative, pk=pk) if pk else None
    if instance and not user_can_manage_initiative(request.user, instance):
        return HttpResponseForbidden('Недостатньо прав доступу.')
    form = InitiativeForm(request.POST or None, request.FILES or None, instance=instance, user=request.user)
    if request.method == 'POST' and form.is_valid():
        initiative = form.save(commit=False)
        initiative.created_by = initiative.created_by or request.user
        initiative.save()
        form.save_m2m()
        form.cleanup_replaced_files(initiative)
        log_action(request.user, 'saved_initiative', initiative)
        messages.success(request, 'Ініціативу збережено.')
        return redirect('manage_initiatives')
    return render(request, 'components/form_page.html', {'form': form, 'title': 'Ініціатива', 'subtitle': 'Створення або редагування місії'})


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
@require_POST
def initiative_delete(request, pk):
    initiative = get_object_or_404(Initiative, pk=pk)
    if not user_can_manage_initiative(request.user, initiative):
        return HttpResponseForbidden('Недостатньо прав доступу.')
    title = initiative.title
    initiative.delete()
    messages.success(request, f'Ініціативу «{title}» видалено.')
    return redirect('manage_initiatives')


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def review_applications(request):
    organizations = managed_organizations_queryset(request.user).order_by('name')
    organization = selected_organization_filter(request, organizations)
    base_initiatives = managed_initiatives_queryset(request.user)
    initiatives = base_initiatives
    if organization:
        initiatives = initiatives.filter(organization_id=organization)
    base_apps = Application.objects.filter(initiative__in=base_initiatives)
    apps = Application.objects.filter(initiative__in=initiatives).select_related('volunteer', 'initiative', 'initiative__organization', 'shift')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if q:
        apps = apps.filter(
            Q(volunteer__full_name__icontains=q) |
            Q(volunteer__email__icontains=q) |
            Q(initiative__title__icontains=q) |
            Q(initiative__organization__name__icontains=q)
        )
    if status in dict(Application.Statuses.choices):
        apps = apps.filter(status=status)
    page_obj = paginate(request, apps.order_by('-created_at'), 12)
    return render(request, 'coordinator/applications_review.html', {
        'applications': page_obj.object_list,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'q': q,
        'organization': organization,
        'organizations': organizations,
        'status': status,
        'application_statuses': Application.Statuses.choices,
        'total_count': base_apps.count(),
        'result_count': page_obj.paginator.count,
    })


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def application_decision(request, pk):
    app = get_object_or_404(
        Application.objects
        .select_related('initiative__organization', 'initiative__category', 'volunteer', 'shift')
        .prefetch_related('initiative__required_skills', 'volunteer__volunteer_skills__skill'),
        pk=pk,
    )
    if not user_can_manage_initiative(request.user, app.initiative):
        return HttpResponseForbidden('Недостатньо прав доступу.')
    form = ApplicationDecisionForm(
        request.POST or None,
        initial={
            'status': app.status,
            'coordinator_comment': app.coordinator_comment,
            'rejection_reason': app.rejection_reason,
        },
        current_status=app.status,
    )
    if request.method == 'POST' and form.is_valid():
        new_status = form.cleaned_data['status']
        if new_status == Application.Statuses.APPROVED:
            ok, reason = application_allowed(app.volunteer, app.initiative, app.shift)
            active_self = app.status in [Application.Statuses.APPROVED, Application.Statuses.ATTENDED]
            if not ok and not active_self:
                messages.error(request, reason)
                return redirect('application_decision', pk=pk)
        old = app.status
        app.status = new_status
        app.coordinator_comment = form.cleaned_data.get('coordinator_comment', '')
        app.rejection_reason = form.cleaned_data.get('rejection_reason', '') if new_status == Application.Statuses.REJECTED else ''
        app.save(update_fields=['status', 'coordinator_comment', 'rejection_reason', 'updated_at'])
        refresh_counts(app)
        notify(app.volunteer, 'application_status', 'Статус заявки змінено', f'Заявка на «{app.initiative.title}»: {app.get_status_display()}.')
        log_action(request.user, 'changed_application_status', app, {'old': old, 'new': new_status})
        messages.success(request, 'Рішення збережено.')
        return redirect('review_applications')
    volunteer_stats = {
        'applications': app.volunteer.applications.count(),
        'approved_hours': app.volunteer.hours.filter(status=VolunteerHour.Statuses.APPROVED).aggregate(total=Sum('hours'))['total'] or 0,
        'certificates': app.volunteer.certificates.count(),
    }
    availability = VolunteerAvailability.objects.filter(volunteer=app.volunteer).first()
    volunteer_skills = [item.skill for item in app.volunteer.volunteer_skills.all()]
    return render(request, 'coordinator/application_decision.html', {
        'form': form,
        'application': app,
        'initiative': app.initiative,
        'volunteer': app.volunteer,
        'volunteer_stats': volunteer_stats,
        'availability': availability,
        'volunteer_skills': volunteer_skills,
    })


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def manage_shifts(request):
    organizations = managed_organizations_queryset(request.user).order_by('name')
    organization = selected_organization_filter(request, organizations)
    base_initiatives = managed_initiatives_queryset(request.user)
    initiatives = base_initiatives
    if organization:
        initiatives = initiatives.filter(organization_id=organization)
    base_shifts = Shift.objects.filter(initiative__in=base_initiatives)
    shifts = Shift.objects.filter(initiative__in=initiatives).select_related('initiative', 'initiative__organization').order_by('shift_date', 'start_time')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    if q:
        shifts = shifts.filter(
            Q(title__icontains=q) |
            Q(initiative__title__icontains=q) |
            Q(initiative__organization__name__icontains=q) |
            Q(location__icontains=q) |
            Q(initiative__city__icontains=q)
        )
    if status in dict(Shift.Statuses.choices):
        shifts = shifts.filter(status=status)
    page_obj = paginate(request, shifts, 12)
    return render(request, 'coordinator/shifts.html', {
        'shifts': page_obj.object_list,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'q': q,
        'organization': organization,
        'organizations': organizations,
        'status': status,
        'shift_statuses': Shift.Statuses.choices,
        'total_count': base_shifts.count(),
        'result_count': page_obj.paginator.count,
    })


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def shift_form(request, pk=None):
    instance = get_object_or_404(Shift, pk=pk) if pk else None
    if instance and not user_can_manage_initiative(request.user, instance.initiative):
        return HttpResponseForbidden('Недостатньо прав доступу.')
    form = ShiftForm(request.POST or None, instance=instance, user=request.user)
    if request.method == 'POST' and form.is_valid():
        shift = form.save()
        log_action(request.user, 'saved_shift', shift)
        messages.success(request, 'Зміну збережено.')
        return redirect('manage_shifts')
    visible_initiatives = form.fields['initiative'].queryset
    occupied_map = {}
    occupied_shifts = Shift.objects.filter(initiative__in=visible_initiatives).select_related('initiative').order_by('shift_date', 'start_time')
    if instance:
        occupied_shifts = occupied_shifts.exclude(pk=instance.pk)
    for item in occupied_shifts:
        occupied_map.setdefault(str(item.initiative_id), []).append({
            'title': item.title,
            'date': item.shift_date.strftime('%d.%m.%Y'),
            'start': item.start_time.strftime('%H:%M'),
            'end': item.end_time.strftime('%H:%M'),
            'location': item.location or item.initiative.city,
            'status': item.get_status_display(),
        })
    return render(request, 'coordinator/shift_form.html', {
        'form': form,
        'title': 'Зміна',
        'subtitle': 'Планування волонтерської місії',
        'occupied_shift_map': occupied_map,
    })


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
@require_POST
def shift_delete(request, pk):
    shift = get_object_or_404(Shift.objects.select_related('initiative'), pk=pk)
    if not user_can_manage_initiative(request.user, shift.initiative):
        return HttpResponseForbidden('Недостатньо прав доступу.')
    title = shift.title
    shift.delete()
    messages.success(request, f'Зміну «{title}» видалено.')
    return redirect('manage_shifts')


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def review_hours(request):
    organizations = managed_organizations_queryset(request.user).order_by('name')
    organization = selected_organization_filter(request, organizations)
    base_initiatives = managed_initiatives_queryset(request.user)
    initiatives = base_initiatives
    if organization:
        initiatives = initiatives.filter(organization_id=organization)
    base_hours = VolunteerHour.objects.filter(initiative__in=base_initiatives)
    hours = VolunteerHour.objects.filter(initiative__in=initiatives).select_related('volunteer', 'initiative', 'initiative__organization', 'shift')
    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    date_from = request.GET.get('date_from', '')
    date_to = request.GET.get('date_to', '')
    parsed_date_from = parse_date(date_from) if date_from else None
    parsed_date_to = parse_date(date_to) if date_to else None
    if q:
        hours = hours.filter(
            Q(volunteer__full_name__icontains=q) |
            Q(volunteer__email__icontains=q) |
            Q(initiative__title__icontains=q) |
            Q(initiative__organization__name__icontains=q) |
            Q(shift__title__icontains=q) |
            Q(description__icontains=q)
        )
    if status in dict(VolunteerHour.Statuses.choices):
        hours = hours.filter(status=status)
    if parsed_date_from:
        hours = hours.filter(submitted_at__date__gte=parsed_date_from)
    if parsed_date_to:
        hours = hours.filter(submitted_at__date__lte=parsed_date_to)
    page_obj = paginate(request, hours.order_by('-submitted_at'), 12)
    return render(request, 'coordinator/hours_review.html', {
        'hours': page_obj.object_list,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'q': q,
        'organization': organization,
        'organizations': organizations,
        'status': status,
        'date_from': date_from,
        'date_to': date_to,
        'hour_statuses': VolunteerHour.Statuses.choices,
        'total_count': base_hours.count(),
        'result_count': page_obj.paginator.count,
    })


@role_required(User.Roles.COORDINATOR, User.Roles.ORGANIZATION_MANAGER)
def hour_decision(request, pk):
    hour = get_object_or_404(
        VolunteerHour.objects.select_related('initiative__organization', 'volunteer', 'shift', 'reviewed_by'),
        pk=pk,
    )
    if not user_can_manage_initiative(request.user, hour.initiative):
        return HttpResponseForbidden('Недостатньо прав доступу.')
    form = HourDecisionForm(request.POST or None, initial={'status': hour.status, 'review_comment': hour.review_comment})
    if request.method == 'POST' and form.is_valid():
        old = hour.status
        hour.status = form.cleaned_data['status']
        hour.review_comment = form.cleaned_data.get('review_comment', '')
        hour.reviewed_by = request.user
        hour.reviewed_at = timezone.now()
        hour.save(update_fields=['status', 'review_comment', 'reviewed_by', 'reviewed_at'])
        if hour.status == VolunteerHour.Statuses.APPROVED:
            issue_certificate_for_hours(hour, request.user)
        notify(hour.volunteer, 'hours_status', 'Години перевірено', f'Запис за «{hour.initiative.title}»: {hour.get_status_display()}.')
        log_action(request.user, 'changed_hour_status', hour, {'old': old, 'new': hour.status})
        messages.success(request, 'Рішення щодо годин збережено.')
        return redirect('review_hours')
    volunteer_stats = {
        'submitted': hour.volunteer.hours.count(),
        'approved': hour.volunteer.hours.filter(status=VolunteerHour.Statuses.APPROVED).count(),
        'approved_hours': hour.volunteer.hours.filter(status=VolunteerHour.Statuses.APPROVED).aggregate(total=Sum('hours'))['total'] or 0,
    }
    return render(request, 'coordinator/hour_decision.html', {
        'form': form,
        'hour': hour,
        'volunteer_stats': volunteer_stats,
    })


@role_required(User.Roles.ADMIN)
def admin_dashboard(request):
    return render(request, 'admin_panel/dashboard.html', {
        'numbers': dashboard_numbers(),
        'recent_logs': __import__('apps.hub.models', fromlist=['AuditLog']).AuditLog.objects.select_related('actor')[:8],
        'categories': InitiativeCategory.objects.annotate(total=Count('initiatives')),
    })


@role_required(User.Roles.ADMIN)
def admin_users(request):
    users = User.objects.all().order_by('role', 'full_name')
    q = request.GET.get('q', '')
    role = request.GET.get('role', '')
    status = request.GET.get('status', '')
    if q:
        users = users.filter(Q(full_name__icontains=q) | Q(email__icontains=q))
    if role:
        users = users.filter(role=role)
    if status:
        users = users.filter(status=status)
    page_obj = paginate(request, users, 12)
    return render(request, 'admin_panel/users.html', {'users': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request), 'roles': User.Roles.choices, 'statuses': User.Statuses.choices})


@role_required(User.Roles.ADMIN)
def admin_user_form(request, pk=None):
    instance = get_object_or_404(User, pk=pk) if pk else None
    form = UserAdminForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        user = form.save(commit=False)
        user.username = user.email
        user.save()
        log_action(request.user, 'saved_user', user)
        messages.success(request, 'Користувача збережено.')
        return redirect('admin_users')
    return render(request, 'components/form_page.html', {'form': form, 'title': 'Користувач', 'subtitle': 'Керування роллю та статусом'})


@role_required(User.Roles.ADMIN)
@require_POST
def admin_user_deactivate(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'Не можна деактивувати власний акаунт.')
        return redirect('admin_users')
    if user.is_platform_admin:
        messages.error(request, 'Статус облікового запису адміністратора змінювати не можна.')
        return redirect('admin_users')
    user.status = User.Statuses.INACTIVE if user.status == User.Statuses.ACTIVE else User.Statuses.ACTIVE
    user.save(update_fields=['status'])
    log_action(request.user, 'toggled_user_status', user, {'status': user.status})
    messages.success(request, 'Статус користувача змінено.')
    return redirect('admin_users')


@role_required(User.Roles.ADMIN)
@require_POST
def admin_user_delete(request, pk):
    user = get_object_or_404(User, pk=pk)
    if user == request.user or user.is_platform_admin:
        messages.error(request, 'Обліковий запис адміністратора видаляти не можна.')
        return redirect('admin_users')
    full_name = user.full_name
    user.delete()
    messages.success(request, f'Користувача «{full_name}» видалено.')
    return redirect('admin_users')


@role_required(User.Roles.ADMIN)
def admin_organizations(request):
    orgs = Organization.objects.select_related('manager').order_by('name')
    page_obj = paginate(request, orgs, 8)
    return render(request, 'admin_panel/organizations.html', {'organizations': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request)})


@role_required(User.Roles.ADMIN)
def organization_form(request, pk=None):
    instance = get_object_or_404(Organization, pk=pk) if pk else None
    form = OrganizationForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        org = form.save()
        log_action(request.user, 'saved_organization', org)
        messages.success(request, 'Організацію збережено.')
        return redirect('admin_organizations')
    return render(request, 'components/form_page.html', {'form': form, 'title': 'Організація', 'subtitle': 'Профіль волонтерської команди'})


@role_required(User.Roles.ADMIN)
@require_POST
def organization_delete(request, pk):
    org = get_object_or_404(Organization, pk=pk)
    name = org.name
    org.delete()
    messages.success(request, f'Організацію «{name}» видалено.')
    return redirect('admin_organizations')


@role_required(User.Roles.ADMIN)
def admin_categories(request):
    categories = InitiativeCategory.objects.annotate(total=Count('initiatives')).order_by('name')
    page_obj = paginate(request, categories, 12)
    return render(request, 'admin_panel/categories.html', {'categories': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request)})


@role_required(User.Roles.ADMIN)
def category_form(request, pk=None):
    instance = get_object_or_404(InitiativeCategory, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request, 'Категорію збережено.'); return redirect('admin_categories')
    return render(request, 'components/form_page.html', {'form': form, 'title': 'Категорія', 'subtitle': 'Напрям волонтерського впливу'})


@role_required(User.Roles.ADMIN)
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(InitiativeCategory, pk=pk)
    name = category.name
    try:
        category.delete()
    except ProtectedError:
        messages.error(request, 'Категорію неможливо видалити, бо до неї прив’язані ініціативи.')
        return redirect('admin_categories')
    messages.success(request, f'Категорію «{name}» видалено.')
    return redirect('admin_categories')


@role_required(User.Roles.ADMIN)
def admin_skills(request):
    skills = Skill.objects.order_by('name')
    page_obj = paginate(request, skills, 12)
    return render(request, 'admin_panel/skills.html', {'skills': page_obj.object_list, 'page_obj': page_obj, 'page_query': pagination_query(request)})


@role_required(User.Roles.ADMIN)
def skill_form(request, pk=None):
    instance = get_object_or_404(Skill, pk=pk) if pk else None
    form = SkillForm(request.POST or None, instance=instance)
    if request.method == 'POST' and form.is_valid():
        form.save(); messages.success(request, 'Навичку збережено.'); return redirect('admin_skills')
    return render(request, 'components/form_page.html', {'form': form, 'title': 'Навичка', 'subtitle': 'Профіль компетенцій волонтера'})


@role_required(User.Roles.ADMIN)
@require_POST
def skill_delete(request, pk):
    skill = get_object_or_404(Skill, pk=pk)
    name = skill.name
    skill.delete()
    messages.success(request, f'Навичку «{name}» видалено.')
    return redirect('admin_skills')


@role_required(User.Roles.ADMIN)
def admin_analytics(request):
    numbers = dashboard_numbers()
    apps_by_status = Application.objects.values('status').annotate(total=Count('id'))
    hours_by_category = InitiativeCategory.objects.annotate(total_hours=Sum('initiatives__hours__hours')).order_by('-total_hours')
    top_volunteers = User.objects.filter(role=User.Roles.VOLUNTEER).annotate(total_hours=Sum('hours__hours')).order_by('-total_hours')[:8]
    return render(request, 'admin_panel/analytics.html', {
        'numbers': numbers,
        'apps_by_status': apps_by_status,
        'hours_by_category': hours_by_category,
        'top_volunteers': top_volunteers,
    })


@role_required(User.Roles.ADMIN)
def admin_volunteer_detail(request, pk):
    person = get_object_or_404(User, pk=pk, role=User.Roles.VOLUNTEER)
    applications = person.applications.select_related('initiative', 'shift').order_by('-created_at')[:12]
    hours = person.hours.select_related('initiative', 'shift').order_by('-submitted_at')[:12]
    certificates = person.certificates.select_related('initiative', 'organization').order_by('-issue_date')[:12]
    threads = person.volunteer_threads.select_related('initiative', 'coordinator').order_by('-updated_at')[:8]
    return render(request, 'admin_panel/volunteer_detail.html', {
        'person': person,
        'applications': applications,
        'hours': hours,
        'certificates': certificates,
        'threads': threads,
        'total_hours': person.hours.filter(status=VolunteerHour.Statuses.APPROVED).aggregate(total=Sum('hours'))['total'] or 0,
    })


@login_required
def notifications(request):
    base_qs = request.user.notifications.all()
    unread_count = base_qs.filter(is_read=False).count()
    notifications_qs = base_qs.order_by('-created_at')
    q = request.GET.get('q', '').strip()
    note_type = request.GET.get('type', '')
    state = request.GET.get('state', '')
    if q:
        notifications_qs = notifications_qs.filter(Q(title__icontains=q) | Q(body__icontains=q))
    if note_type:
        notifications_qs = notifications_qs.filter(type=note_type)
    if state == 'unread':
        notifications_qs = notifications_qs.filter(is_read=False)
    elif state == 'read':
        notifications_qs = notifications_qs.filter(is_read=True)
    page_obj = paginate(request, notifications_qs, 12)
    request.user.notifications.filter(is_read=False).update(is_read=True)
    cache.delete(f'header-stats:{request.user.id}')
    return render(request, 'notifications/list.html', {
        'notifications': page_obj.object_list,
        'page_obj': page_obj,
        'page_query': pagination_query(request),
        'filters': request.GET,
        'types': base_qs.order_by('type').values_list('type', flat=True).distinct(),
        'unread_count': unread_count,
        'total_notifications': base_qs.count(),
    })
