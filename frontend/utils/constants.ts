export const COOKIE_MAX_AGE_1_YEAR = 365 * 24 * 60 * 60

export const TAMPING_TYPES = [
	'Tamping luar',
	'Tamping AO',
	'Tamping Pembinaan',
	'Tamping kunjungan',
	'Tamping kamtib',
	'Tamping kunci',
	'Tamping klinik',
	'Tamping dapur',
	'Tamping mesjid',
	'Tamping p2u',
	'Tamping BLK',
	'Tamping kebersihan',
	'Tamping Humas',
	'Tamping kebun',
] as const

export const TAMPING_OPTION_ITEMS = TAMPING_TYPES.map(item => ({ title: item, value: item }))
