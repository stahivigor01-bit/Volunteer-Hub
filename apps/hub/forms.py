from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from .models import (
    Application, Initiative, InitiativeCategory, Message, Organization, Shift, Skill,
    User, VolunteerAvailability, VolunteerHour,
)
from .utils import unique_slug


class PhotoFileInput(forms.FileInput):
    input_type = 'file'


class StyledFormMixin:
    use_required_attribute = False

    def _merge_widget_class(self, widget, *classes):
        existing = widget.attrs.get('class', '')
        merged = [name for name in existing.split() if name]
        for class_name in classes:
            if class_name and class_name not in merged:
                merged.append(class_name)
        widget.attrs['class'] = ' '.join(merged)

    def _style_fields(self):
        for field in self.fields.values():
            widget = field.widget
            base = 'form-control'
            if isinstance(widget, forms.CheckboxSelectMultiple):
                continue
            elif isinstance(widget, forms.CheckboxInput):
                self._merge_widget_class(widget, 'check-input')
            elif isinstance(widget, forms.SelectMultiple):
                self._merge_widget_class(widget, 'form-control', 'multi-control')
            else:
                self._merge_widget_class(widget, base)


class ManagedFileFormMixin:
    managed_file_fields = {}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_file_names = {}
        for field_name, remove_field in self.managed_file_fields.items():
            original = getattr(self.instance, field_name, None) if getattr(self, 'instance', None) else None
            self._original_file_names[field_name] = original.name if original else ''
            self._mark_photo_upload(field_name, original)
            if self._original_file_names[field_name]:
                self.fields[remove_field] = forms.BooleanField(
                    label='Видалити поточний файл',
                    required=False,
                    widget=forms.CheckboxInput(attrs={'class': 'check-input danger-check photo-remove-input', 'data-photo-remove-for': field_name}),
                )

    def _mark_photo_upload(self, field_name, original):
        form_field = self.fields.get(field_name)
        if not isinstance(form_field, forms.ImageField):
            return

        form_field.widget = PhotoFileInput(attrs=form_field.widget.attrs)
        widget = form_field.widget
        widget.attrs['data-photo-upload'] = '1'
        widget.attrs['accept'] = 'image/*'
        existing = widget.attrs.get('class', '')
        classes = [name for name in existing.split() if name]
        if 'photo-upload-input' not in classes:
            classes.append('photo-upload-input')
        widget.attrs['class'] = ' '.join(classes)
        if original and original.name:
            try:
                widget.attrs['data-current-url'] = original.url
            except ValueError:
                pass

    def _apply_file_removals(self, instance):
        for field_name, remove_field in self.managed_file_fields.items():
            if self.cleaned_data.get(remove_field):
                file_field = getattr(instance, field_name)
                file_field.name = ''

    def cleanup_replaced_files(self, instance=None):
        instance = instance or self.instance
        for field_name in self.managed_file_fields:
            old_name = self._original_file_names.get(field_name, '')
            current_file = getattr(instance, field_name)
            current_name = current_file.name if current_file else ''
            if old_name and old_name != current_name:
                current_file.storage.delete(old_name)

    def save(self, commit=True):
        instance = super().save(commit=False)
        self._apply_file_removals(instance)
        if commit:
            instance.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()
            self.cleanup_replaced_files(instance)
        return instance


class RegisterForm(StyledFormMixin, UserCreationForm):
    full_name = forms.CharField(label='ПІБ', max_length=160)
    email = forms.EmailField(label='Email')
    phone = forms.CharField(label='Телефон', max_length=32, required=False)
    city = forms.CharField(label='Місто', max_length=100, required=False)

    class Meta:
        model = User
        fields = ['full_name', 'email', 'phone', 'city', 'password1', 'password2']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()
        self.fields['password1'].label = 'Пароль'
        self.fields['password2'].label = 'Повторіть пароль'

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        if User.objects.filter(email=email).exists():
            raise ValidationError('Користувач із таким email уже існує.')
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.email = self.cleaned_data['email']
        user.full_name = self.cleaned_data['full_name']
        user.phone = self.cleaned_data.get('phone', '')
        user.city = self.cleaned_data.get('city', '')
        user.role = User.Roles.VOLUNTEER
        if commit:
            user.save()
        return user


class LoginForm(StyledFormMixin, forms.Form):
    email = forms.EmailField(label='Email')
    password = forms.CharField(label='Пароль', widget=forms.PasswordInput)

    def __init__(self, request, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.request = request
        self.user = None
        self._style_fields()

    def clean(self):
        data = super().clean()
        email = data.get('email', '').lower().strip()
        password = data.get('password')
        if email and password:
            self.user = authenticate(self.request, username=email, password=password)
            if self.user is None:
                raise ValidationError('Невірний email або пароль.')
            if self.user.status != User.Statuses.ACTIVE:
                raise ValidationError('Обліковий запис деактивовано.')
        return data


class ProfileForm(ManagedFileFormMixin, StyledFormMixin, forms.ModelForm):
    managed_file_fields = {'avatar': 'remove_avatar'}

    class Meta:
        model = User
        fields = ['full_name', 'phone', 'city', 'bio', 'avatar']
        labels = {'full_name': 'ПІБ', 'phone': 'Телефон', 'city': 'Місто', 'bio': 'Про себе', 'avatar': 'Аватар'}
        widgets = {'bio': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class UserAdminForm(ProfileForm):
    managed_file_fields = {}

    class Meta(ProfileForm.Meta):
        model = User
        fields = ['full_name', 'email', 'phone', 'city', 'role', 'status', 'bio']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        role_field = self.fields['role']
        if self.instance.pk and self.instance.is_platform_admin:
            role_field.choices = [(User.Roles.ADMIN, User.Roles.ADMIN.label)]
            role_field.disabled = True
            self.fields['status'].disabled = True
        else:
            role_field.choices = [
                choice for choice in User.Roles.choices
                if choice[0] != User.Roles.ADMIN
            ]

    def clean_email(self):
        email = self.cleaned_data['email'].lower().strip()
        qs = User.objects.filter(email=email)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Такий email уже використовується.')
        return email

    def clean_role(self):
        role = self.cleaned_data.get('role')
        if role == User.Roles.ADMIN and not (self.instance.pk and self.instance.is_platform_admin):
            raise ValidationError('Створювати або призначати нових адміністраторів не можна.')
        return role


class OrganizationForm(ManagedFileFormMixin, StyledFormMixin, forms.ModelForm):
    managed_file_fields = {'logo': 'remove_logo'}

    class Meta:
        model = Organization
        fields = ['name', 'description', 'logo', 'city', 'address', 'contact_email', 'phone', 'website', 'status', 'manager', 'coordinators']
        labels = {'manager': 'Менеджер', 'coordinators': 'Координатори'}
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coordinators'].widget = forms.CheckboxSelectMultiple()
        self._style_fields()
        self.fields['manager'].queryset = User.objects.filter(role=User.Roles.ORGANIZATION_MANAGER)
        self.fields['coordinators'].queryset = User.objects.filter(role=User.Roles.COORDINATOR)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.slug = unique_slug(Organization, instance.name, self.instance, fallback='organization')
        if commit:
            instance.save()
            self.save_m2m()
            self.cleanup_replaced_files(instance)
        return instance


class ManagerOrganizationForm(ManagedFileFormMixin, StyledFormMixin, forms.ModelForm):
    managed_file_fields = {'logo': 'remove_logo'}

    class Meta:
        model = Organization
        fields = ['name', 'description', 'logo', 'city', 'address', 'contact_email', 'phone', 'website', 'coordinators']
        labels = {
            'name': 'Назва організації',
            'description': 'Опис',
            'logo': 'Логотип',
            'city': 'Місто',
            'address': 'Адреса',
            'contact_email': 'Контактний email',
            'phone': 'Телефон',
            'website': 'Сайт',
            'coordinators': 'Координатори',
        }
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}
        help_texts = {
            'coordinators': 'Оберіть координаторів, які працюють із заявками, змінами та годинами цієї організації.',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['coordinators'].widget = forms.CheckboxSelectMultiple()
        coordinators = User.objects.filter(role=User.Roles.COORDINATOR)
        if self.instance.pk:
            coordinators = coordinators.filter(Q(status=User.Statuses.ACTIVE) | Q(coordinated_organizations=self.instance)).distinct()
        else:
            coordinators = coordinators.filter(status=User.Statuses.ACTIVE)
        self.fields['coordinators'].queryset = coordinators.order_by('full_name')
        self._style_fields()

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.slug = unique_slug(Organization, instance.name, self.instance, fallback='organization')
        if commit:
            instance.save()
            self.save_m2m()
            self.cleanup_replaced_files(instance)
        return instance


class InitiativeForm(ManagedFileFormMixin, StyledFormMixin, forms.ModelForm):
    managed_file_fields = {'image': 'remove_image'}

    class Meta:
        model = Initiative
        fields = [
            'organization', 'category', 'title', 'short_description', 'description', 'image',
            'urgency_level', 'format', 'city', 'location_address', 'start_date', 'end_date',
            'required_volunteers_count', 'required_skills', 'beginner_friendly', 'accessibility_notes',
            'safety_notes', 'contact_person', 'expected_impact', 'status',
        ]
        widgets = {
            'start_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'end_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'description': forms.Textarea(attrs={'rows': 5}),
            'short_description': forms.Textarea(attrs={'rows': 2}),
            'accessibility_notes': forms.Textarea(attrs={'rows': 3}),
            'safety_notes': forms.Textarea(attrs={'rows': 3}),
            'required_skills': forms.CheckboxSelectMultiple(),
        }
        labels = {
            'organization': 'Організація',
            'category': 'Категорія',
            'required_skills': 'Потрібні навички',
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self._style_fields()
        if user and user.role == User.Roles.COORDINATOR:
            self.fields['organization'].queryset = user.coordinated_organizations.all()
        elif user and user.role == User.Roles.ORGANIZATION_MANAGER:
            self.fields['organization'].queryset = user.managed_organizations.all()

    def clean(self):
        data = super().clean()
        start = data.get('start_date')
        end = data.get('end_date')
        if start and end and end < start:
            raise ValidationError('Дата завершення не може бути раніше дати початку.')
        if data.get('required_volunteers_count', 0) <= 0:
            raise ValidationError('Кількість волонтерів має бути більшою за нуль.')
        return data

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.slug = unique_slug(Initiative, instance.title, self.instance, fallback='initiative')
        if commit:
            instance.save()
            self.save_m2m()
            self.cleanup_replaced_files(instance)
        return instance


class ShiftForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Shift
        fields = ['initiative', 'title', 'shift_date', 'start_time', 'end_time', 'location', 'max_volunteers', 'status']
        labels = {
            'initiative': 'Ініціатива',
            'title': 'Назва зміни',
            'shift_date': 'Дата',
            'start_time': 'Початок',
            'end_time': 'Завершення',
            'location': 'Місце',
            'max_volunteers': 'Максимум волонтерів',
            'status': 'Статус',
        }
        widgets = {
            'shift_date': forms.DateInput(format='%Y-%m-%d', attrs={'type': 'date'}),
            'start_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
            'end_time': forms.TimeInput(format='%H:%M', attrs={'type': 'time'}),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        self._style_fields()
        if user and user.role == User.Roles.COORDINATOR:
            self.fields['initiative'].queryset = Initiative.objects.filter(organization__in=user.coordinated_organizations.all())
        elif user and user.role == User.Roles.ORGANIZATION_MANAGER:
            self.fields['initiative'].queryset = Initiative.objects.filter(organization__manager=user)

    def clean(self):
        data = super().clean()
        if data.get('start_time') and data.get('end_time') and data['end_time'] <= data['start_time']:
            raise ValidationError('Час завершення має бути пізніше часу початку.')
        if data.get('max_volunteers', 0) <= 0:
            raise ValidationError('Максимальна кількість волонтерів має бути більшою за нуль.')
        initiative = data.get('initiative')
        shift_date = data.get('shift_date')
        start_time = data.get('start_time')
        end_time = data.get('end_time')
        if initiative and shift_date and start_time and end_time:
            conflicts = Shift.objects.filter(
                initiative=initiative,
                shift_date=shift_date,
                start_time__lt=end_time,
                end_time__gt=start_time,
            )
            if self.instance.pk:
                conflicts = conflicts.exclude(pk=self.instance.pk)
            conflict = conflicts.order_by('start_time').first()
            if conflict:
                raise ValidationError(
                    f'У цієї ініціативи вже є зміна «{conflict.title}» '
                    f'{conflict.start_time:%H:%M}–{conflict.end_time:%H:%M} на цю дату.'
                )
        return data


class ApplicationForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Application
        fields = ['shift', 'motivation_text']
        labels = {'shift': 'Зміна', 'motivation_text': 'Чому хочете долучитися?'}
        widgets = {'motivation_text': forms.Textarea(attrs={'rows': 5, 'placeholder': 'Коротко опишіть мотивацію та досвід...'})}

    def __init__(self, initiative, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initiative = initiative
        self.fields['shift'].queryset = initiative.shifts.filter(status=Shift.Statuses.OPEN)
        self.fields['shift'].required = False
        self._style_fields()

    def clean_motivation_text(self):
        text = self.cleaned_data['motivation_text'].strip()
        if len(text) < 15:
            raise ValidationError('Напишіть щонайменше 15 символів мотивації.')
        return text


class ApplicationDecisionForm(StyledFormMixin, forms.Form):
    status = forms.ChoiceField(label='Рішення', choices=[
        (Application.Statuses.UNDER_REVIEW, 'На розгляді'),
        (Application.Statuses.APPROVED, 'Підтвердити'),
        (Application.Statuses.REJECTED, 'Відхилити'),
        (Application.Statuses.ATTENDED, 'Участь підтверджена'),
        (Application.Statuses.MISSED, 'Не з’явився'),
    ])
    coordinator_comment = forms.CharField(label='Коментар', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    rejection_reason = forms.CharField(label='Причина відхилення', required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        current_status = kwargs.pop('current_status', None)
        super().__init__(*args, **kwargs)
        if current_status == Application.Statuses.CANCELLED:
            choices = list(self.fields['status'].choices)
            if not any(value == Application.Statuses.CANCELLED for value, _ in choices):
                self.fields['status'].choices = [
                    (Application.Statuses.CANCELLED, 'Скасована волонтером'),
                    *choices,
                ]
        self._style_fields()

    def clean(self):
        data = super().clean()
        if data.get('status') == Application.Statuses.REJECTED and not data.get('rejection_reason'):
            raise ValidationError('Для відхилення заявки потрібно вказати причину.')
        return data


class CancelApplicationForm(StyledFormMixin, forms.Form):
    reason = forms.CharField(label='Причина скасування', widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class VolunteerHourForm(ManagedFileFormMixin, StyledFormMixin, forms.ModelForm):
    managed_file_fields = {'evidence_file': 'remove_evidence_file'}

    class Meta:
        model = VolunteerHour
        fields = ['initiative', 'shift', 'hours', 'description', 'evidence_file']
        labels = {
            'initiative': 'Ініціатива',
            'shift': 'Зміна',
            'hours': 'Години',
            'description': 'Опис виконаної роботи',
            'evidence_file': 'Файл підтвердження',
        }
        widgets = {'description': forms.Textarea(attrs={'rows': 4})}

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        approved_apps = Application.objects.filter(volunteer=user, status__in=[Application.Statuses.APPROVED, Application.Statuses.ATTENDED])
        self.fields['initiative'].queryset = Initiative.objects.filter(applications__in=approved_apps).distinct()
        self.fields['shift'].queryset = Shift.objects.filter(applications__in=approved_apps).distinct()
        self.fields['initiative'].empty_label = 'Оберіть ініціативу'
        self.fields['shift'].empty_label = 'Без конкретної зміни'
        self.fields['shift'].required = False
        self._style_fields()
        self.fields['evidence_file'].widget.attrs['data-file-upload'] = '1'

    def clean_hours(self):
        hours = self.cleaned_data['hours']
        if hours <= 0:
            raise ValidationError('Кількість годин має бути більшою за нуль.')
        return hours


class HourDecisionForm(StyledFormMixin, forms.Form):
    status = forms.ChoiceField(label='Рішення', choices=[
        (VolunteerHour.Statuses.APPROVED, 'Підтвердити'),
        (VolunteerHour.Statuses.REJECTED, 'Відхилити'),
    ])
    review_comment = forms.CharField(label='Коментар', required=False, widget=forms.Textarea(attrs={'rows': 3}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class MessageForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Message
        fields = ['message_text']
        labels = {'message_text': 'Повідомлення'}
        widgets = {'message_text': forms.Textarea(attrs={'rows': 4, 'placeholder': 'Напишіть повідомлення...'})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._style_fields()


class AvailabilityForm(StyledFormMixin, forms.ModelForm):
    skills = forms.ModelMultipleChoiceField(label='Навички', queryset=Skill.objects.all(), required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = VolunteerAvailability
        fields = ['weekdays', 'weekends', 'mornings', 'afternoons', 'evenings', 'remote_only', 'preferred_city']

    def __init__(self, user, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user
        self.fields['skills'].initial = [vs.skill_id for vs in user.volunteer_skills.all()]
        self._style_fields()


class CategoryForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = InitiativeCategory
        fields = ['name', 'description', 'icon', 'color']
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self._style_fields()

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        qs = InitiativeCategory.objects.filter(name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError('Категорія з такою назвою вже існує.')
        return name

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.slug = unique_slug(InitiativeCategory, instance.name, self.instance, fallback='category')
        if commit:
            instance.save()
            if hasattr(self, 'save_m2m'):
                self.save_m2m()
        return instance


class SkillForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Skill
        fields = ['name', 'category']
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs); self._style_fields()
