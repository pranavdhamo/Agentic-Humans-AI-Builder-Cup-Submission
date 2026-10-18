package com.agentichumans.carddemo.intcalc;

import com.agentichumans.carddemo.cobol.FixedRecordReader;
import com.agentichumans.carddemo.cobol.Records;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.LocalDateTime;
import java.util.function.Supplier;
import org.springframework.batch.core.Job;
import org.springframework.batch.core.Step;
import org.springframework.batch.core.job.builder.JobBuilder;
import org.springframework.batch.core.repository.JobRepository;
import org.springframework.batch.core.step.builder.StepBuilder;
import org.springframework.batch.core.step.tasklet.Tasklet;
import org.springframework.batch.item.ItemWriter;
import org.springframework.batch.repeat.RepeatStatus;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;

/**
 * Job "intcalc" = CBACT04C (monthly interest). Inputs: state after POSTTRAN (ACCTDATA.flat, TCATBALF.flat in
 * {@code carddemo.state-dir}) plus the reference files cardxref.txt / discgrp.txt in {@code carddemo.input-dir}.
 */
@Configuration
@ConditionalOnProperty(name = "carddemo.job", havingValue = "intcalc")
class InterestJobConfig {

    @Bean InterestState interestState() { return new InterestState(); }

    @Bean Supplier<LocalDateTime> clock() { return LocalDateTime::now; }

    @Bean InterestLedger interestLedger(@Value("${carddemo.state-dir}") Path stateDir,
                                        @Value("${carddemo.input-dir}") Path inputDir) throws IOException {
        return InterestLedger.load(stateDir, inputDir);
    }

    @Bean FixedRecordReader tcatBalReader(@Value("${carddemo.state-dir}") Path stateDir) {
        return new FixedRecordReader(stateDir.resolve("TCATBALF.flat"), Records.TCATBAL_LEN);
    }

    @Bean InterestProcessor interestProcessor(InterestLedger ledger, InterestState state, Supplier<LocalDateTime> clock,
                                              @Value("${carddemo.int-date}") String intDate,
                                              @Value("${carddemo.intcalc.fix-last-account:false}") boolean fixLast) {
        if (intDate.length() != 10) throw new IllegalArgumentException("carddemo.int-date must be YYYY-MM-DD");
        return new InterestProcessor(ledger, state, intDate, fixLast, clock);
    }

    @Bean ItemWriter<String> interestWriter(InterestState state) {
        return chunk -> chunk.forEach(state.interestTransactions::add);
    }

    @Bean Step interestStep(JobRepository repo, PlatformTransactionManager tx, FixedRecordReader tcatBalReader,
                            InterestProcessor processor, ItemWriter<String> interestWriter) {
        return new StepBuilder("computeInterest", repo).<String, String>chunk(10, tx)
                .reader(tcatBalReader).processor(processor).writer(interestWriter).build();
    }

    @Bean Tasklet writeInterestOutputs(InterestState state, InterestLedger ledger, InterestProcessor processor,
                                       @Value("${carddemo.output-dir}") Path outDir) {
        return (contribution, ctx) -> {
            processor.endOfFile();
            Files.createDirectories(outDir);
            write(outDir.resolve("SYSTRAN.ps"), String.join("", state.interestTransactions));
            StringBuilder accts = new StringBuilder();
            ledger.accounts.values().forEach(a -> accts.append(a.raw()));
            write(outDir.resolve("ACCTDATA.flat"), accts.toString());
            write(outDir.resolve("stdout.txt"), String.format("START OF EXECUTION OF PROGRAM CBACT04C%n"
                    + "END OF EXECUTION OF PROGRAM CBACT04C%n"));
            write(outDir.resolve("rc.txt"), state.returnCode() + "\n");
            return RepeatStatus.FINISHED;
        };
    }

    private static void write(Path p, String s) throws IOException {
        Files.write(p, s.getBytes(StandardCharsets.ISO_8859_1));
    }

    @Bean Step interestOutputStep(JobRepository repo, PlatformTransactionManager tx, Tasklet writeInterestOutputs) {
        return new StepBuilder("writeInterestOutputs", repo).tasklet(writeInterestOutputs, tx).build();
    }

    @Bean Job interestJob(JobRepository repo, Step interestStep, Step interestOutputStep) {
        return new JobBuilder("intcalc", repo).start(interestStep).next(interestOutputStep).build();
    }
}
