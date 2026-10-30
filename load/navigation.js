export function validateNavigation(config) {
    if (config.model !== 'pagination-visits-v3'
            || config.forward_visit_ratio !== 0.9
            || !Number.isInteger(config.minimum_reads_per_visit)
            || !Number.isInteger(config.maximum_reads_per_visit)
            || config.minimum_reads_per_visit < 4
            || config.maximum_reads_per_visit < config.minimum_reads_per_visit
            || config.maximum_reads_per_visit > 100
            || !Number.isFinite(config.local_return_ratio)
            || config.local_return_ratio < 0 || config.local_return_ratio > 1) {
        throw new Error('Configuração de navegação incompatível.');
    }
}

export class PaginationJourney {
    constructor(next, totalPages, config) {
        validateNavigation(config);
        if (!Number.isInteger(totalPages) || totalPages < 1) {
            throw new Error('A navegação exige ao menos uma página.');
        }
        this.random = next;
        this.lastPage = totalPages - 1;
        this.config = config;
        this.remainingReads = 0;
        this.page = 0;
        this.direction = 'forward';
        this.entering = true;
    }

    current() {
        const newVisit = this.remainingReads === 0;
        if (newVisit) {
            this.direction = this.random() < this.config.forward_visit_ratio ? 'forward' : 'reverse';
            const lengths = this.config.maximum_reads_per_visit - this.config.minimum_reads_per_visit + 1;
            this.remainingReads = this.config.minimum_reads_per_visit + Math.floor(this.random() * lengths);
            this.page = 0;
            this.entering = true;
        }
        return {
            page: this.page,
            direction: this.direction,
            newVisit,
            pageClass: this.page === 0 ? 'first' : this.page === this.lastPage ? 'last' : 'intermediate',
        };
    }

    completed() {
        this.remainingReads -= 1;
        if (this.remainingReads === 0 || this.lastPage === 0) {
            this.remainingReads = 0;
            return;
        }
        if (this.direction === 'reverse') {
            if (this.entering) {
                this.page = this.lastPage;
                this.entering = false;
            } else if (this.page > 1) {
                this.page -= 1;
            } else {
                this.remainingReads = 0;
            }
            return;
        }
        if (this.page === this.lastPage) {
            this.remainingReads = 0;
        } else if (this.page > 0 && this.random() < this.config.local_return_ratio) {
            this.page -= 1;
        } else {
            this.page += 1;
        }
    }
}
