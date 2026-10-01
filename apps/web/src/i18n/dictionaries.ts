export const LOCALES = ['en', 'ar'] as const;
export type Locale = (typeof LOCALES)[number];
export const DEFAULT_LOCALE: Locale = 'en';
export const LOCALE_COOKIE = 'locale';

export function dir(locale: Locale): 'ltr' | 'rtl' {
  return locale === 'ar' ? 'rtl' : 'ltr';
}

type Dict = Record<string, string>;

const en: Dict = {
  appName: 'MeasureX',
  tagline: 'Shipment dimensioning & weighing',
  employeeId: 'Employee ID',
  password: 'Password',
  signIn: 'Sign in',
  signingIn: 'Signing in…',
  signOut: 'Sign out',
  language: 'العربية',
  loginError: 'Invalid employee ID or password',
  accountLocked: 'Account locked. Try again in 15 minutes.',
  changePasswordTitle: 'Change your password',
  changePasswordHint: 'You must set a new password before continuing.',
  currentPassword: 'Current password',
  newPassword: 'New password',
  confirmPassword: 'Confirm new password',
  save: 'Save',
  saving: 'Saving…',
  passwordsDoNotMatch: 'Passwords do not match',
  passwordTooShort: 'Password must be at least 8 characters',
  changePasswordError: 'Could not change password. Check your current password.',
  dashboard: 'Dashboard',
  welcome: 'Welcome',
  role: 'Role',
  roleLabour: 'Labour',
  roleTeamLeader: 'Team Leader',
  roleAdmin: 'Admin',
  dashboardEmpty: 'Dashboard content arrives in Milestone 4.',
};

const ar: Dict = {
  appName: 'ميجرإكس',
  tagline: 'قياس أبعاد ووزن الشحنات',
  employeeId: 'رقم الموظف',
  password: 'كلمة المرور',
  signIn: 'تسجيل الدخول',
  signingIn: 'جارٍ تسجيل الدخول…',
  signOut: 'تسجيل الخروج',
  language: 'English',
  loginError: 'رقم الموظف أو كلمة المرور غير صحيحة',
  accountLocked: 'تم قفل الحساب. حاول مرة أخرى بعد 15 دقيقة.',
  changePasswordTitle: 'غيّر كلمة المرور',
  changePasswordHint: 'يجب تعيين كلمة مرور جديدة قبل المتابعة.',
  currentPassword: 'كلمة المرور الحالية',
  newPassword: 'كلمة المرور الجديدة',
  confirmPassword: 'تأكيد كلمة المرور الجديدة',
  save: 'حفظ',
  saving: 'جارٍ الحفظ…',
  passwordsDoNotMatch: 'كلمتا المرور غير متطابقتين',
  passwordTooShort: 'يجب أن تكون كلمة المرور 8 أحرف على الأقل',
  changePasswordError: 'تعذّر تغيير كلمة المرور. تحقق من كلمة المرور الحالية.',
  dashboard: 'لوحة التحكم',
  welcome: 'مرحباً',
  role: 'الدور',
  roleLabour: 'عامل',
  roleTeamLeader: 'قائد الفريق',
  roleAdmin: 'مسؤول',
  dashboardEmpty: 'محتوى لوحة التحكم يصل في المرحلة الرابعة.',
};

const dictionaries: Record<Locale, Dict> = { en, ar };

export function getDictionary(locale: Locale): Dict {
  return dictionaries[locale] ?? dictionaries[DEFAULT_LOCALE];
}
